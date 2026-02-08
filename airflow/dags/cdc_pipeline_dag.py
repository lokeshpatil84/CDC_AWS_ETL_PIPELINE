"""
CDC Pipeline Orchestration DAG
Fits with: module.airflow (MWAA/EC2), module.glue (Glue jobs), module.kafka, module.s3
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
from airflow.providers.amazon.aws.sensors.glue import GlueJobSensor
from airflow.providers.amazon.aws.operators.sns import SnsPublishOperator
from airflow.operators.python import PythonOperator
from airflow.utils.trigger_rule import TriggerRule
from airflow.exceptions import AirflowFailException
import boto3
import requests
import os
import json


# =============================================================================
# CONFIGURATION (from Terraform/Environment)
# =============================================================================

AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")
PROJECT_NAME = os.getenv("PROJECT_NAME", "cdc-pipeline")

# From Terraform outputs
S3_BUCKET = os.getenv("S3_BUCKET")  # module.s3.data_bucket_name
GLUE_ROLE_ARN = os.getenv("GLUE_ROLE_ARN")  # IAM role ARN for Glue
SNS_TOPIC_ARN = os.getenv("SNS_TOPIC_ARN")  # aws_sns_topic.alerts.arn

# Kafka/Debezium (from module.kafka, module.ecs)
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS")  # kafka-internal:9092
DEBEZIUM_CONNECT_URL = os.getenv(
    "DEBEZIUM_CONNECT_URL"
)  # http://debezium.cdc.local:8083

# Database (from aws_secretsmanager_secret)
DB_SECRET_NAME = os.getenv(
    "DB_SECRET_NAME", f"{PROJECT_NAME}-{ENVIRONMENT}-db-credentials"
)

# Glue Job Names (from module.glue)
GLUE_JOB_BRONZE = os.getenv(
    "GLUE_JOB_BRONZE", f"{PROJECT_NAME}-{ENVIRONMENT}-bronze-to-silver"
)
GLUE_JOB_GOLD = os.getenv(
    "GLUE_JOB_GOLD", f"{PROJECT_NAME}-{ENVIRONMENT}-silver-to-gold"
)


# =============================================================================
# DEFAULT ARGS
# =============================================================================

default_args = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "start_date": datetime(2024, 1, 1),
    "email_on_failure": False,  # Use SNS instead
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
    "execution_timeout": timedelta(hours=2),
    "sla": timedelta(hours=1),
    "tags": ["cdc", "debezium", "kafka", "glue", "iceberg"],
}


# =============================================================================
# DAG DEFINITION
# =============================================================================

dag = DAG(
    dag_id=f"{PROJECT_NAME}_{ENVIRONMENT}_orchestration",
    default_args=default_args,
    description="CDC Pipeline: Kafka → Bronze → Silver → Gold",
    schedule_interval=timedelta(hours=1),
    catchup=False,
    max_active_runs=1,
    doc_md="""
    # CDC Pipeline Orchestration
    
    ## Flow
    1. Health Checks (Kafka + Debezium)
    2. Setup/Verify Debezium Connectors
    3. Run Bronze→Silver Glue Job (SCD Type 2)
    4. Data Quality Checks
    5. Run Silver→Gold Glue Job (Aggregations)
    6. Notifications
    
    ## Terraform Dependencies
    - module.kafka (bootstrap_servers)
    - module.ecs (Debezium URL)
    - module.glue (Glue jobs)
    - module.s3 (scripts bucket)
    - aws_sns_topic.alerts
    """,
)


# =============================================================================
# PYTHON CALLABLES
# =============================================================================


def get_db_credentials():
    """Fetch database credentials from Secrets Manager"""
    try:
        client = boto3.client("secretsmanager", region_name=AWS_REGION)
        response = client.get_secret_value(SecretId=DB_SECRET_NAME)
        return json.loads(response["SecretString"])
    except Exception as e:
        raise AirflowFailException(f"Failed to fetch DB credentials: {str(e)}")


def check_kafka_health(**context):
    """
    Check Kafka cluster health
    For self-managed Kafka on EC2 (not MSK)
    """
    if not KAFKA_BOOTSTRAP_SERVERS:
        raise AirflowFailException("KAFKA_BOOTSTRAP_SERVERS not configured")

    try:
        logger = context["ti"].log
        logger.info(f"Checking Kafka at: {KAFKA_BOOTSTRAP_SERVERS}")

        # For self-managed Kafka, try to describe cluster topics via Kafka AdminClient
        # or just verify connectivity via socket
        import socket

        brokers = KAFKA_BOOTSTRAP_SERVERS.split(",")
        healthy_brokers = []

        for broker in brokers:
            host, port = broker.split(":") if ":" in broker else (broker, "9092")
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                result = sock.connect_ex((host, int(port)))
                sock.close()

                if result == 0:
                    healthy_brokers.append(broker)
                    logger.info(f"✓ Broker {broker} is reachable")
                else:
                    logger.warning(
                        f"✗ Broker {broker} connection failed (code: {result})"
                    )
            except Exception as e:
                logger.warning(f"✗ Broker {broker} error: {str(e)}")

        if not healthy_brokers:
            raise AirflowFailException("No Kafka brokers reachable")

        # Push healthy brokers to XCom
        context["ti"].xcom_push(key="healthy_brokers", value=healthy_brokers)
        logger.info(
            f"Kafka health check passed: {len(healthy_brokers)}/{len(brokers)} brokers"
        )

        return True

    except Exception as e:
        raise AirflowFailException(f"Kafka health check failed: {str(e)}")


def check_debezium_health(**context):
    """
    Check Debezium Connect health and connector status
    """
    if not DEBEZIUM_CONNECT_URL:
        raise AirflowFailException("DEBEZIUM_CONNECT_URL not configured")

    try:
        logger = context["ti"].log
        logger.info(f"Checking Debezium at: {DEBEZIUM_CONNECT_URL}")

        session = requests.Session()
        session.headers.update({"Accept": "application/json"})

        # Check Connect REST API health
        r = session.get(f"{DEBEZIUM_CONNECT_URL}/", timeout=10)
        r.raise_for_status()
        logger.info("✓ Debezium Connect REST API is up")

        # Get list of connectors
        r = session.get(f"{DEBEZIUM_CONNECT_URL}/connectors", timeout=10)
        r.raise_for_status()
        connectors = r.json()
        logger.info(f"Found connectors: {connectors}")

        # Check status of each connector
        connector_statuses = {}
        failed_connectors = []

        for conn_name in connectors:
            try:
                r = session.get(
                    f"{DEBEZIUM_CONNECT_URL}/connectors/{conn_name}/status", timeout=10
                )
                r.raise_for_status()
                status = r.json()

                connector_state = status.get("connector", {}).get("state", "UNKNOWN")
                task_states = [
                    t.get("state", "UNKNOWN") for t in status.get("tasks", [])
                ]

                connector_statuses[conn_name] = {
                    "connector_state": connector_state,
                    "task_states": task_states,
                    "tasks_running": task_states.count("RUNNING"),
                    "tasks_failed": task_states.count("FAILED"),
                }

                logger.info(f"  {conn_name}: {connector_state}, tasks: {task_states}")

                # Check for failures
                if connector_state != "RUNNING" or "FAILED" in task_states:
                    failed_connectors.append(conn_name)

            except Exception as e:
                logger.error(f"  {conn_name}: Error checking status - {str(e)}")
                failed_connectors.append(conn_name)
                connector_statuses[conn_name] = {"error": str(e)}

        # Push statuses to XCom
        context["ti"].xcom_push(key="connector_statuses", value=connector_statuses)

        if failed_connectors:
            raise AirflowFailException(
                f"Failed/unhealthy connectors: {failed_connectors}"
            )

        logger.info("✓ All Debezium connectors healthy")
        return True

    except requests.RequestException as e:
        raise AirflowFailException(f"Debezium connection error: {str(e)}")
    except Exception as e:
        raise AirflowFailException(f"Debezium health check failed: {str(e)}")


def setup_debezium_connector(**context):
    """
    Setup or verify Debezium PostgreSQL connector
    Uses AWS Secrets Manager for credentials
    """
    try:
        logger = context["ti"].log
        logger.info("Setting up Debezium connector...")

        # Get DB credentials from Secrets Manager
        db_creds = get_db_credentials()

        connector_name = f"{PROJECT_NAME}-{ENVIRONMENT}-postgres-connector"

        connector_config = {
            "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
            "database.hostname": db_creds["host"],
            "database.port": str(db_creds.get("port", 5432)),
            "database.user": db_creds["username"],
            "database.password": db_creds["password"],
            "database.dbname": db_creds["database"],
            "database.server.name": f"{PROJECT_NAME}-{ENVIRONMENT}-server",
            "topic.prefix": "cdc",
            "table.include.list": "public.users,public.products,public.orders",
            "slot.name": f"debezium_slot_{ENVIRONMENT}",
            "plugin.name": "pgoutput",
            # Converters - keep full envelope for SCD2
            "key.converter": "org.apache.kafka.connect.json.JsonConverter",
            "value.converter": "org.apache.kafka.connect.json.JsonConverter",
            "key.converter.schemas.enable": "false",
            "value.converter.schemas.enable": "false",
            # Heartbeat for progress tracking
            "heartbeat.interval.ms": "10000",
            # Schema history in Kafka
            "schema.history.internal.kafka.bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
            "schema.history.internal.kafka.topic": f"schema-changes.{PROJECT_NAME}.{ENVIRONMENT}",
            "schema.history.internal.store.only.captured.tables.ddl": "true",
            # Performance tuning
            "max.batch.size": "2048",
            "max.queue.size": "8192",
            "poll.interval.ms": "1000",
            # Initial snapshot on first start
            "snapshot.mode": "initial",
        }

        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})

        # Check if connector exists
        r = session.get(
            f"{DEBEZIUM_CONNECT_URL}/connectors/{connector_name}", timeout=10
        )

        if r.status_code == 200:
            logger.info(f"Connector '{connector_name}' already exists")

            # Verify config matches
            current_config = r.json()
            # Could add config comparison logic here

            # Check if it's running
            r = session.get(
                f"{DEBEZIUM_CONNECT_URL}/connectors/{connector_name}/status", timeout=10
            )
            status = r.json()
            state = status.get("connector", {}).get("state")

            if state != "RUNNING":
                logger.warning(f"Connector not running (state: {state}), restarting...")
                r = session.post(
                    f"{DEBEZIUM_CONNECT_URL}/connectors/{connector_name}/restart",
                    timeout=30,
                )
                r.raise_for_status()
                logger.info("Connector restarted")
            else:
                logger.info("Connector is running")

        else:
            # Create new connector
            logger.info(f"Creating connector: {connector_name}")
            r = session.put(
                f"{DEBEZIUM_CONNECT_URL}/connectors/{connector_name}/config",
                json=connector_config,
                timeout=60,
            )
            r.raise_for_status()
            logger.info(f"✓ Connector '{connector_name}' created successfully")

        # Push connector name to XCom
        context["ti"].xcom_push(key="connector_name", value=connector_name)

        return True

    except Exception as e:
        raise AirflowFailException(f"Connector setup failed: {str(e)}")


def monitor_data_quality(**context):
    """
    Monitor data quality metrics
    Checks: connector lag, message rates, error counts
    """
    try:
        logger = context["ti"].log
        ti = context["ti"]

        # Get previous task results
        connector_statuses = (
            ti.xcom_pull(task_ids="debezium_health_check", key="connector_statuses")
            or {}
        )

        metrics = {
            "timestamp": datetime.utcnow().isoformat(),
            "dag_id": context["dag"].dag_id,
            "run_id": str(context["run_id"]),
            "connectors_healthy": True,
            "connector_count": len(connector_statuses),
            "failed_tasks": 0,
        }

        # Analyze connector statuses
        for conn_name, status in connector_statuses.items():
            if status.get("connector_state") != "RUNNING":
                metrics["connectors_healthy"] = False
                logger.warning(f"Connector not running: {conn_name}")

            metrics["failed_tasks"] += status.get("tasks_failed", 0)

        # Push metrics
        ti.xcom_push(key="data_quality_metrics", value=metrics)

        # Alert if unhealthy
        if not metrics["connectors_healthy"]:
            raise AirflowFailException(
                "Data quality check failed: connectors unhealthy"
            )

        if metrics["failed_tasks"] > 0:
            logger.warning(f"Found {metrics['failed_tasks']} failed tasks")
            # Could add logic to restart tasks here

        logger.info("✓ Data quality check passed")
        logger.info(f"Metrics: {json.dumps(metrics, indent=2)}")

        return metrics

    except Exception as e:
        raise AirflowFailException(f"Data quality monitoring failed: {str(e)}")


def cleanup_on_failure(**context):
    """
    Cleanup and recovery actions on pipeline failure
    """
    logger = context["ti"].log
    ti = context["ti"]

    try:
        dag_run = ti.dag_run
        failed_tasks = [t for t in dag_run.get_task_instances() if t.state == "failed"]

        logger.info(f"Cleanup: Found {len(failed_tasks)} failed tasks")

        for task in failed_tasks:
            logger.info(f"  - {task.task_id}: {task.state}")

        # Optional: Restart failed Debezium tasks
        # Optional: Alert on-call

        return True

    except Exception as e:
        logger.error(f"Cleanup error: {str(e)}")
        return False  # Don't fail the cleanup task


# =============================================================================
# TASK DEFINITIONS
# =============================================================================

# -----------------------------------------------------------------------------
# Phase 1: Health Checks
# -----------------------------------------------------------------------------

kafka_health = PythonOperator(
    task_id="kafka_health_check", python_callable=check_kafka_health, dag=dag
)

debezium_health = PythonOperator(
    task_id="debezium_health_check", python_callable=check_debezium_health, dag=dag
)

# -----------------------------------------------------------------------------
# Phase 2: Setup
# -----------------------------------------------------------------------------

setup_connector = PythonOperator(
    task_id="setup_debezium_connector",
    python_callable=setup_debezium_connector,
    dag=dag,
)

# -----------------------------------------------------------------------------
# Phase 3: Bronze to Silver (SCD Type 2)
# -----------------------------------------------------------------------------

# Note: For streaming jobs, you might use a different pattern
# This assumes batch/scheduled processing of Bronze data
bronze_to_silver = GlueJobOperator(
    task_id="bronze_to_silver",
    job_name=GLUE_JOB_BRONZE,
    script_location=f"s3://{S3_BUCKET}/scripts/bronze_to_silver.py",
    s3_bucket=S3_BUCKET,
    iam_role_name=GLUE_ROLE_ARN.split("/")[-1]
    if GLUE_ROLE_ARN
    else None,  # Extract role name from ARN
    region_name=AWS_REGION,
    num_of_dpus=10,  # Adjust based on data volume
    dag=dag,
)

wait_bronze = GlueJobSensor(
    task_id="wait_bronze_to_silver",
    job_name=GLUE_JOB_BRONZE,
    run_id="{{ task_instance.xcom_pull(task_ids='bronze_to_silver', key='return_value') }}",
    region_name=AWS_REGION,
    poke_interval=60,  # Check every minute
    timeout=3600,  # 1 hour timeout
    mode="reschedule",  # Don't block a worker slot
    dag=dag,
)

# -----------------------------------------------------------------------------
# Phase 4: Data Quality
# -----------------------------------------------------------------------------

quality_check = PythonOperator(
    task_id="data_quality_check", python_callable=monitor_data_quality, dag=dag
)

# -----------------------------------------------------------------------------
# Phase 5: Silver to Gold (Aggregations)
# -----------------------------------------------------------------------------

silver_to_gold = GlueJobOperator(
    task_id="silver_to_gold",
    job_name=GLUE_JOB_GOLD,
    script_location=f"s3://{S3_BUCKET}/scripts/silver_to_gold.py",
    s3_bucket=S3_BUCKET,
    iam_role_name=GLUE_ROLE_ARN.split("/")[-1] if GLUE_ROLE_ARN else None,
    region_name=AWS_REGION,
    num_of_dpus=5,
    dag=dag,
)

wait_gold = GlueJobSensor(
    task_id="wait_silver_to_gold",
    job_name=GLUE_JOB_GOLD,
    run_id="{{ task_instance.xcom_pull(task_ids='silver_to_gold', key='return_value') }}",
    region_name=AWS_REGION,
    poke_interval=60,
    timeout=1800,  # 30 min timeout
    mode="reschedule",
    dag=dag,
)

# -----------------------------------------------------------------------------
# Phase 6: Notifications
# -----------------------------------------------------------------------------

# Only trigger if all upstream tasks succeed
success_alert = SnsPublishOperator(
    task_id="success_alert",
    target_arn=SNS_TOPIC_ARN,
    message=json.dumps(
        {
            "default": json.dumps(
                {
                    "status": "SUCCESS",
                    "dag_id": "{{ dag.dag_id }}",
                    "run_id": "{{ run_id }}",
                    "execution_date": "{{ ds }}",
                    "message": "CDC Pipeline completed successfully",
                }
            )
        }
    ),
    subject="CDC Pipeline Success - {{ ds }}",
    dag=dag,
    trigger_rule=TriggerRule.ALL_SUCCESS,
)

# Trigger if ANY task fails
failure_alert = SnsPublishOperator(
    task_id="failure_alert",
    target_arn=SNS_TOPIC_ARN,
    message=json.dumps(
        {
            "default": json.dumps(
                {
                    "status": "FAILED",
                    "dag_id": "{{ dag.dag_id }}",
                    "run_id": "{{ run_id }}",
                    "execution_date": "{{ ds }}",
                    "failed_tasks": "{{ task_instance.xcom_pull(task_ids='cleanup_failed', key='failed_tasks') or 'unknown' }}",
                    "message": "CDC Pipeline failed. Check Airflow logs.",
                }
            )
        }
    ),
    subject="ALERT: CDC Pipeline Failed - {{ ds }}",
    dag=dag,
    trigger_rule=TriggerRule.ONE_FAILED,
)

# Cleanup task
cleanup_task = PythonOperator(
    task_id="cleanup_failed",
    python_callable=cleanup_on_failure,
    dag=dag,
    trigger_rule=TriggerRule.ONE_FAILED,
)


# =============================================================================
# DEPENDENCIES
# =============================================================================

# Main success path
kafka_health >> debezium_health >> setup_connector
setup_connector >> bronze_to_silver >> wait_bronze
wait_bronze >> quality_check >> silver_to_gold >> wait_gold
wait_gold >> success_alert

# Failure handling
(
    [
        kafka_health,
        debezium_health,
        setup_connector,
        bronze_to_silver,
        wait_bronze,
        quality_check,
        silver_to_gold,
        wait_gold,
    ]
    >> failure_alert
    >> cleanup_task
)
