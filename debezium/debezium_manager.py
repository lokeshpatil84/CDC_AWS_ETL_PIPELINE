"""
Debezium Connector Manager
Manages Debezium connectors for PostgreSQL CDC
Fits with: module.ecs (Debezium running in ECS), aws_db_instance.postgres
"""

import json
import requests
import sys
import os
import time
from typing import Dict, List, Optional


class DebeziumConnectorManager:
    def __init__(self, connect_url: str = None):
        self.connect_url = connect_url or os.getenv(
            "DEBEZIUM_CONNECT_URL", "http://localhost:8083"
        )
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def health_check(self) -> bool:
        """Check if Debezium Connect is available"""
        try:
            response = self.session.get(f"{self.connect_url}/", timeout=5)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def get_connectors(self) -> List[str]:
        """List all connectors"""
        try:
            response = self.session.get(f"{self.connect_url}/connectors", timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Error fetching connectors: {e}")
            return []

    def get_connector_status(self, connector_name: str) -> Optional[Dict]:
        """Get detailed connector status"""
        try:
            response = self.session.get(
                f"{self.connect_url}/connectors/{connector_name}/status", timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Error fetching status: {e}")
            return None

    def create_postgresql_connector(
        self,
        connector_name: str,
        database_host: str,
        database_port: int,
        database_name: str,
        database_user: str,
        database_password: str,
        tables: List[str] = None,
        slot_name: str = "debezium_slot",
        kafka_topic_prefix: str = "cdc",
    ) -> bool:
        """Create Debezium PostgreSQL connector"""
        tables = tables or ["users", "products", "orders"]

        # Connector configuration - KEEP FULL CDC ENVELOPE (no unwrap)
        # This preserves before/after for SCD Type 2
        connector_config = {
            "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
            "database.hostname": database_host,
            "database.port": str(database_port),
            "database.user": database_user,
            "database.password": database_password,
            "database.dbname": database_name,
            "database.server.name": f"{connector_name}-server",
            "topic.prefix": kafka_topic_prefix,
            "table.include.list": ",".join([f"public.{t}" for t in tables]),
            "plugin.name": "pgoutput",
            # Key/Value converters - keep as JSON, no schema (simpler)
            "key.converter": "org.apache.kafka.connect.json.JsonConverter",
            "value.converter": "org.apache.kafka.connect.json.JsonConverter",
            "key.converter.schemas.enable": "false",
            "value.converter.schemas.enable": "false",
            # NO UNWRAP TRANSFORM - we need full envelope for SCD2
            # "transforms": "unwrap",
            # "transforms.unwrap.type": "io.debezium.transforms.ExtractNewRecordState",
            # Heartbeat for progress monitoring
            "heartbeat.interval.ms": "10000",
            "heartbeat.action.query": "INSERT INTO public.debezium_heartbeat (id, ts) VALUES (1, NOW()) ON CONFLICT (id) DO UPDATE SET ts = EXCLUDED.ts;",
            # Slot and publication
            "slot.name": slot_name,
            "publication.name": "dbz_publication",
            # Initial snapshot
            "snapshot.mode": "initial",
            # Performance
            "max.batch.size": "2048",
            "max.queue.size": "8192",
            "poll.interval.ms": "1000",
            # Schema history (stored in Kafka topic)
            "schema.history.internal.kafka.bootstrap.servers": os.getenv(
                "KAFKA_BOOTSTRAP_SERVERS", "kafka:29092"
            ),
            "schema.history.internal.kafka.topic": f"schema-changes.{database_name}",
            "schema.history.internal.store.only.captured.tables.ddl": "true",
        }

        try:
            print(f"Creating connector: {connector_name}")
            print(f"Database: {database_host}:{database_port}/{database_name}")
            print(f"Tables: {tables}")

            response = self.session.put(
                f"{self.connect_url}/connectors/{connector_name}/config",
                json=connector_config,
                timeout=60,
            )
            response.raise_for_status()
            print(f"✓ Connector '{connector_name}' created successfully!")
            return True

        except requests.RequestException as e:
            print(f"✗ Error creating connector: {e}")
            if hasattr(e, "response") and e.response is not None:
                print(f"Response: {e.response.text}")
            return False

    def delete_connector(self, connector_name: str) -> bool:
        """Delete a connector"""
        try:
            response = self.session.delete(
                f"{self.connect_url}/connectors/{connector_name}", timeout=30
            )
            response.raise_for_status()
            print(f"✓ Connector '{connector_name}' deleted!")
            return True
        except requests.RequestException as e:
            print(f"✗ Error deleting: {e}")
            return False

    def pause_connector(self, connector_name: str) -> bool:
        """Pause connector"""
        try:
            response = self.session.put(
                f"{self.connect_url}/connectors/{connector_name}/pause", timeout=30
            )
            response.raise_for_status()
            print(f"✓ Connector '{connector_name}' paused!")
            return True
        except requests.RequestException as e:
            print(f"✗ Error pausing: {e}")
            return False

    def resume_connector(self, connector_name: str) -> bool:
        """Resume connector"""
        try:
            response = self.session.put(
                f"{self.connect_url}/connectors/{connector_name}/resume", timeout=30
            )
            response.raise_for_status()
            print(f"✓ Connector '{connector_name}' resumed!")
            return True
        except requests.RequestException as e:
            print(f"✗ Error resuming: {e}")
            return False

    def restart_connector(self, connector_name: str) -> bool:
        """Restart connector"""
        try:
            response = self.session.post(
                f"{self.connect_url}/connectors/{connector_name}/restart", timeout=30
            )
            response.raise_for_status()
            print(f"✓ Connector '{connector_name}' restart initiated!")
            return True
        except requests.RequestException as e:
            print(f"✗ Error restarting: {e}")
            return False

    def restart_task(self, connector_name: str, task_id: int) -> bool:
        """Restart specific task"""
        try:
            response = self.session.post(
                f"{self.connect_url}/connectors/{connector_name}/tasks/{task_id}/restart",
                timeout=30,
            )
            response.raise_for_status()
            print(f"✓ Task {task_id} restarted!")
            return True
        except requests.RequestException as e:
            print(f"✗ Error restarting task: {e}")
            return False

    def get_connector_topics(self, connector_name: str) -> List[str]:
        """Get list of topics connector is writing to"""
        try:
            response = self.session.get(
                f"{self.connect_url}/connectors/{connector_name}/topics", timeout=10
            )
            response.raise_for_status()
            return response.json().get("topics", [])
        except requests.RequestException as e:
            print(f"Error fetching topics: {e}")
            return []


def setup_local():
    """Setup for local Docker environment"""
    manager = DebeziumConnectorManager("http://localhost:8083")

    # Wait for Debezium to be ready
    print("Waiting for Debezium Connect...")
    for i in range(30):
        if manager.health_check():
            print("✓ Debezium Connect is ready!")
            break
        time.sleep(2)
        print(f"  Retry {i+1}/30...")
    else:
        print("✗ Debezium Connect not available")
        sys.exit(1)

    # Check existing
    existing = manager.get_connectors()
    print(f"Existing connectors: {existing}")

    # Create connector
    success = manager.create_postgresql_connector(
        connector_name="cdc-postgres-connector",
        database_host=os.getenv("DB_HOST", "postgres"),
        database_port=int(os.getenv("DB_PORT", "5432")),
        database_name=os.getenv("DB_NAME", "cdc_demo"),
        database_user=os.getenv("DB_USER", "postgres"),
        database_password=os.getenv("DB_PASSWORD", "postgres"),
        tables=["users", "products", "orders"],
        slot_name="debezium_slot",
        kafka_topic_prefix="cdc",
    )

    if success:
        time.sleep(5)
        status = manager.get_connector_status("cdc-postgres-connector")
        print(f"\nStatus: {json.dumps(status, indent=2)}")

        topics = manager.get_connector_topics("cdc-postgres-connector")
        print(f"\nTopics: {topics}")


def setup_aws():
    """Setup for AWS environment (ECS/EC2)"""
    # Get Debezium URL from environment (ECS service discovery or ALB)
    connect_url = os.getenv("DEBEZIUM_CONNECT_URL")
    if not connect_url:
        print("Error: DEBEZIUM_CONNECT_URL not set")
        sys.exit(1)

    manager = DebeziumConnectorManager(connect_url)

    # Get DB credentials from Secrets Manager (from Terraform aws_secretsmanager_secret)
    secret_name = os.getenv("DB_SECRET_NAME", "cdc-pipeline-dev-db-credentials")

    try:
        import boto3

        secrets_client = boto3.client(
            "secretsmanager", region_name=os.getenv("AWS_REGION", "ap-south-1")
        )
        secret = secrets_client.get_secret_value(SecretId=secret_name)
        credentials = json.loads(secret["SecretString"])
    except Exception as e:
        print(f"Error fetching secret {secret_name}: {e}")
        sys.exit(1)

    # Create connector
    success = manager.create_postgresql_connector(
        connector_name="cdc-postgres-connector",
        database_host=credentials["host"],
        database_port=int(credentials["port"]),
        database_name=credentials["database"],
        database_user=credentials["username"],
        database_password=credentials["password"],
        tables=["users", "products", "orders"],
        slot_name="debezium_slot_aws",
        kafka_topic_prefix="cdc",
    )

    if success:
        print("\nWaiting for connector to start...")
        time.sleep(10)
        status = manager.get_connector_status("cdc-postgres-connector")
        print(f"Status: {json.dumps(status, indent=2)}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Debezium Connector Manager")
    parser.add_argument("--local", action="store_true", help="Setup for local Docker")
    parser.add_argument("--aws", action="store_true", help="Setup for AWS")
    parser.add_argument("--url", type=str, help="Debezium Connect URL")
    parser.add_argument("--list", action="store_true", help="List connectors")
    parser.add_argument("--status", type=str, help="Check connector status")
    parser.add_argument("--delete", type=str, help="Delete connector")
    parser.add_argument("--restart", type=str, help="Restart connector")
    parser.add_argument("--pause", type=str, help="Pause connector")
    parser.add_argument("--resume", type=str, help="Resume connector")

    args = parser.parse_args()

    if args.local:
        setup_local()
    elif args.aws:
        setup_aws()
    elif args.url:
        # Custom URL operations
        manager = DebeziumConnectorManager(args.url)
        if args.list:
            connectors = manager.get_connectors()
            print(f"Connectors: {json.dumps(connectors, indent=2)}")
        elif args.status:
            status = manager.get_connector_status(args.status)
            print(f"Status: {json.dumps(status, indent=2)}")
        elif args.delete:
            manager.delete_connector(args.delete)
        elif args.restart:
            manager.restart_connector(args.restart)
        elif args.pause:
            manager.pause_connector(args.pause)
        elif args.resume:
            manager.resume_connector(args.resume)
        else:
            parser.print_help()
    else:
        parser.print_help()
