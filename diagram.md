ascii
                                          AWS CLOUD (Region: ap-south-1)
+------------------------------------------------------------------------------------------------------------------+
|  VPC (10.0.0.0/16)                                                                                               |
|                                                                                                                  |
|  [1] REAL-TIME INGESTION LAYER (Continuous Stream)                                                               |
|  +-------------------+      +---------------------+      +---------------------+      +-----------------------+  |
|  |  Source Database  | WAL  |    CDC Connector    | JSON |   Message Broker    |Stream|   Ingestion Job       |  |
|  |                   +----->+                     +----->+                     +----->+                       |  |
|  |   [PostgreSQL]    |Stream|     [Debezium]      |Topic |   [Apache Kafka]    |      |     [AWS Glue]        |  |
|  |      (RDS)        |      |    (ECS Fargate)    |      |   (EC2 t3.small)    |      |  (kafka_to_bronze.py) |  |
|  +---------+---------+      +----------+----------+      +----------+----------+      +-----------+-----------+  |
|            ^                           ^                            ^                             |              |
|            |                           | REST API (:8083)           | Port 9092                   | Writes JSON  |
|            |                           |                            |                             v              |
|  +---------+---------+                 |                 +----------+----------+      +-----------+-----------+  |
|  |  Secrets Manager  |                 |                 |      SNS Topic      |      |     Bronze Layer      |  |
|  | (DB Credentials)  |                 |                 |       (Alerts)      |      |      (S3 Bucket)      |  |
|  +-------------------+                 |                 +----------+----------+      |       Raw JSON        |  |
|                                        |                            ^                 +-----------+-----------+  |
|                                        |                            |                             |              |
|                                        |                            | 6. Alerts                   | Reads        |
|  [2] CONTROL PLANE (Orchestration)     |                            |                             |              |
|  +-------------------------------------+----------------------------+-----------------------------|-----------+  |
|  |                       Apache Airflow (ECS Fargate)                                             |           |  |
|  |                       DAG: cdc_pipeline_dag.py                                                 |           |  |
|  |                                                                                                |           |  |
|  |   1. Health Checks  -----> (Socket Check Kafka / HTTP Check Debezium)                          |           |  |
|  |   2. Setup Connector ----> (PUT Config to Debezium REST API)                                   |           |  |
|  |   3. Data Quality -------> (Monitor Connector Lag/Status)                                      |           |  |
|  |   4. Trigger Batch Jobs -> (Trigger Glue via Boto3) -------------------------------------------+           |  |
|  |                                                                                                            |  |
|  +------------------------------------------------------------------------------------------------------------+  |
|                                                                                                                  |
|  [3] BATCH PROCESSING LAYER (Medallion Architecture)                                                             |
|                                                                                                                  |
|      +-------------------------+             +-------------------------+             +-------------------------+ |
|      |    Transformation       |             |      Silver Layer       |             |      Aggregation        | |
|      |      (Glue Job)       --+------------>|      (S3 Bucket)      --+------------>|       (Glue Job)        | |
|      | (bronze_to_silver.py)   | Writes      |    Apache Iceberg       | Reads       |  (silver_to_gold.py)    | |
|      |     [SCD Type 2]        |             |     [Clean Data]        |             |     [Business KPIs]     | |
|      +-------------------------+             +-------------------------+             +------------+------------+ |
|                                                                                                   |              |
|                                                                                                   | Writes       |
|                                                                                                   v              |
|                                                                                      +------------+------------+ |
|                                                                                      |       Gold Layer        | |
|                                                                                      |       (S3 Bucket)       | |
|                                                                                      |     Apache Iceberg      | |
|                                                                                      |    [Aggregated Data]    | |
|                                                                                      +-------------------------+ |
+------------------------------------------------------------------------------------------------------------------+
Process Flow (A to Z):
Source: Data changes in RDS PostgreSQL are captured by the Debezium connector running on ECS Fargate.
Stream: Debezium pushes these changes as JSON messages to Apache Kafka (running on EC2) topics.
Ingest: A streaming process (likely kafka_to_bronze.py) reads from Kafka and dumps raw JSON files into the Bronze S3 Bucket.
Orchestrate: Airflow (on ECS) wakes up hourly:
Checks health of Kafka and Debezium.
Ensures the Debezium connector is configured correctly via REST API.
Triggers the Bronze -> Silver Glue job.
Transform: The Glue job reads raw JSON, handles schema evolution and SCD Type 2 logic, and writes to Silver S3 in Iceberg format.
Aggregate: Airflow triggers the Silver -> Gold Glue job to create business aggregates (daily summaries) in Gold S3.
Alert: If any step fails, Airflow publishes a message to SNS for email alerts.