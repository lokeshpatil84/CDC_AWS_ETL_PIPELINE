┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              AWS CLOUD (ap-south-1)                                      │
│                                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐    │
│  │                         TERRAFORM INFRASTRUCTURE                                 │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │    │
│  │  │ module.vpc  │  │  module.s3  │  │ module.ecs  │  │module.kafka │              │    │
│  │  │  (VPC+SG)   │  │ (Data Lake) │  │  Debezium   │  │ Kafka EC2   │              │    │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘              │    │
│  │         └─────────────────┴─────────────────┴─────────────────┘                    │    │
│  │                              │                                                    │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                              │    │
│  │  │module.glue  │  │module.airflow│  │    RDS      │                              │    │
│  │  │ ETL Jobs   │  │Orchestration │  │ PostgreSQL  │                              │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                              │    │
│  └─────────────────────────────────────────────────────────────────────────────────┘    │
│                                           │                                              │
└───────────────────────────────────────────┼──────────────────────────────────────────────┘
                                            │
┌───────────────────────────────────────────┼──────────────────────────────────────────────┐
│                                           ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│  │                           INGESTION LAYER                                         │   │
│  │                                                                                   │   │
│  │   ┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐  │   │
│  │   │   PostgreSQL    │         │    Debezium     │         │  Apache Kafka   │  │   │
│  │   │   (RDS)         │──WAL──▶│   (ECS Fargate) │──JSON──▶│  (EC2 KRaft)    │  │   │
│  │   │                 │         │                 │         │                 │  │   │
│  │   │ • users table   │         │ • CDC Connector │         │ • cdc.db.users  │  │   │
│  │   │ • products table│         │ • Slot: dbz_    │         │ • cdc.db.products│  │   │
│  │   │ • orders table  │         │   publication   │         │ • cdc.db.orders │  │   │
│  │   │ • WAL logical   │         │ • Heartbeat     │         │ • Internal:9092 │  │   │
│  │   │   replication   │         │ • Schema History│         │                 │  │   │
│  │   └─────────────────┘         └─────────────────┘         └────────┬────────┘  │   │
│  │                                                                    │            │   │
│  │   Secrets Manager: db-credentials                                  │            │   │
│  │   (host, port, username, password)                                 │            │   │
│  │                                                                    ▼            │   │
│  └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                        │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│  │                      STREAMING PROCESSING LAYER (AWS Glue)                        │   │
│  │                                                                                   │   │
│  │   ┌─────────────────────────────────────────────────────────────────────────┐    │   │
│  │   │                    KAFKA TO BRONZE (Streaming Job)                     │    │   │
│  │   │  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────┐    │    │   │
│  │   │  │ Read Kafka  │──▶│ Parse CDC   │──▶│ Write to S3 Bronze      │    │    │   │
│  │   │  │ (Spark      │    │ Events      │    │ (Apache Iceberg)        │    │    │   │
│  │   │  │  Streaming) │    │ • operation │    │                         │    │    │   │
│  │   │  │             │    │ • before    │    │ Table: bronze_cdc_events│    │    │   │
│  │   │  │ Topics:     │    │ • after     │    │ Partition: source_table │    │    │   │
│  │   │  │ cdc.db.*    │    │ • source    │    │         + days()        │    │    │   │
│  │   │  └─────────────┘    │ • ts_ms     │    │                         │    │    │   │
│  │   │                     └─────────────┘    │ DLQ: dlq/bronze/         │    │    │   │
│  │   │                                        │ (bad records)           │    │    │   │
│  │   └─────────────────────────────────────────────────────────────────────────┘    │   │
│  │                                          │                                       │   │
│  │                                          ▼                                       │   │
│  │   ┌─────────────────────────────────────────────────────────────────────────┐    │   │
│  │   │                   BRONZE TO SILVER (Batch Job)                         │    │   │
│  │   │  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────┐    │    │   │
│  │   │  │ Read Bronze │──▶│ SCD Type 2  │──▶│ Write to S3 Silver      │    │    │   │
│  │   │  │ (Iceberg)   │    │ Transform   │    │ (Apache Iceberg)        │    │    │   │
│  │   │  │             │    │             │    │                         │    │    │   │
│  │   │  │ Tables:     │    │ • Parse JSON│    │ Tables:                 │    │    │   │
│  │   │  │ users       │    │ • Deduplicate│   │ • silver_users          │    │    │   │
│  │   │  │ products    │    │ • Generate  │    │ • silver_products       │    │    │   │
│  │   │  │ orders      │    │   _hash     │    │ • silver_orders         │    │    │   │
│  │   │  │             │    │ • MERGE     │    │                         │    │    │   │
│  │   │  │ Incremental │    │   (SCD2)    │    │ SCD Type 2 Columns:     │    │    │   │
│  │   │  │ (watermark) │    │             │    │ • _valid_from           │    │    │   │
│  │   │  │             │    │ Transforms: │    │ • _valid_to             │    │    │   │
│  │   │  │             │    │ • email_    │    │ • _is_current           │    │    │   │
│  │   │  │             │    │   domain    │    │ • _hash                 │    │    │   │
│  │   │  │             │    │ • price_    │    │ • operation             │    │    │   │
│  │   │  │             │    │   category  │    │                         │    │    │   │
│  │   │  └─────────────┘    └─────────────┘    └─────────────────────────┘    │    │   │
│  │   └─────────────────────────────────────────────────────────────────────────┘    │   │
│  │                                          │                                       │   │
│  │                                          ▼                                       │   │
│  │   ┌─────────────────────────────────────────────────────────────────────────┐    │   │
│  │   │                   SILVER TO GOLD (Batch Job)                           │    │   │
│  │   │  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────┐    │    │   │
│  │   │  │ Read Silver │──▶│ Business    │──▶│ Write to S3 Gold        │    │    │   │
│  │   │  │ (Iceberg)   │    │ Aggregations│    │ (Apache Iceberg)        │    │    │   │
│  │   │  │             │    │             │    │                         │    │    │   │
│  │   │  │ Filter:     │    │ Analytics:  │    │ Tables:                 │    │    │   │
│  │   │  │ _is_current │    │             │    │ • gold_user_analytics   │    │    │   │
│  │   │  │ = true      │    │ • RFM       │    │ • gold_product_analytics│    │    │   │
│  │   │  │             │    │   Analysis  │    │ • gold_sales_summary    │    │    │   │
│  │   │  │ Joins:      │    │ • Product   │    │                         │    │    │   │
│  │   │  │ users +     │    │   Performance│   │ Segments:               │    │    │   │
│  │   │  │ orders      │    │ • Daily     │    │ • VIP (>1000)           │    │    │   │
│  │   │  │             │    │   Sales     │    │ • Loyal (>500)          │    │    │   │
│  │   │  │             │    │   Summary   │    │ • Frequent (>5 orders)  │    │    │   │
│  │   │  │             │    │             │    │ • New                   │    │    │   │
│  │   │  └─────────────┘    └─────────────┘    └─────────────────────────┘    │    │   │
│  │   └─────────────────────────────────────────────────────────────────────────┘    │   │
│  └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                        │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│  │                         DATA LAKE STORAGE (S3)                                    │   │
│  │                                                                                   │   │
│  │   s3://{bucket}/iceberg/                                                          │   │
│  │   ├── bronze_cdc_events/      ← Raw CDC JSON events                               │   │
│  │   ├── silver_users/           ← SCD Type 2 current + history                     │   │
│  │   ├── silver_products/        ← Price category, is_active                         │   │
│  │   ├── silver_orders/          ← Order value category                            │   │
│  │   ├── gold_user_analytics/    ← RFM segmentation                                │   │
│  │   ├── gold_product_analytics/ ← Performance tiers                               │   │
│  │   └── gold_sales_summary/     ← Daily aggregates                                  │   │
│  │                                                                                   │   │
│  │   s3://{bucket}/checkpoints/   ← Spark streaming checkpoints                      │   │
│  │   s3://{bucket}/dlq/           ← Dead letter queue                                │   │
│  │   s3://{bucket}/scripts/       ← Glue job scripts                               │   │
│  └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                        │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│  │                      ORCHESTRATION & MONITORING                                 │   │
│  │                                                                                   │   │
│  │   ┌─────────────────────────────────────────────────────────────────────────┐    │   │
│  │   │                    APACHE AIRFLOW (ECS Fargate)                          │    │   │
│  │   │                                                                          │    │   │
│  │   │   DAG: cdc_pipeline_orchestration                                          │    │   │
│  │   │   Schedule: Every 1 hour                                                   │    │   │
│  │   │                                                                          │    │   │
│  │   │   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                   │    │   │
│  │   │   │  Phase 1:   │──▶│  Phase 2:   │──▶│  Phase 3:   │                   │    │   │
│  │   │   │Health Checks│    │   Setup     │    │ Bronze→Silver                  │    │   │
│  │   │   │             │    │             │    │ (SCD Type 2)│                   │    │   │
│  │   │   │• Kafka      │    │• Debezium   │    │             │                   │    │   │
│  │   │   │  Health     │    │  Connector  │    │             │                   │    │   │
│  │   │   │• Debezium   │    │             │    │             │                   │    │   │
│  │   │   │  Health     │    │             │    │             │                   │    │   │
│  │   │   └─────────────┘    └─────────────┘    └──────┬──────┘                   │    │   │
│  │   │                                                │                          │    │   │
│  │   │   ┌─────────────┐    ┌─────────────┐          │                          │    │   │
│  │   │   │  Phase 6:   │◀───│  Phase 5:   │◀─────────┘                          │    │   │
│  │   │   │ Notification│    │ Silver→Gold │                                     │    │   │
│  │   │   │             │    │(Aggregations)│                                     │    │   │
│  │   │   │• SNS Success│    │             │                                     │    │   │
│  │   │   │• SNS Failure│    │             │                                     │    │   │
│  │   │   │             │    │             │                                     │    │   │
│  │   │   └─────────────┘    └──────┬──────┘                                     │    │   │
│  │   │                             │                                            │    │   │
│  │   │   ┌─────────────┐◀──────────┘                                            │    │   │
│  │   │   │  Phase 4:   │                                                        │    │   │
│  │   │   │Data Quality │                                                        │    │   │
│  │   │   │   Check     │                                                        │    │   │
│  │   │   └─────────────┘                                                        │    │   │
│  │   │                                                                          │    │   │
│  │   │   Failure Path: Any task fails → SNS Alert → Cleanup Task                │    │   │
│  │   └─────────────────────────────────────────────────────────────────────────┘    │   │
│  │                                                                                   │   │
│  │   ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                  │   │
│  │   │  CloudWatch     │  │   SNS Topic     │  │  Cost Alarms    │                  │   │
│  │   │  Logs/Metrics   │  │   Alerts        │  │  (Billing)      │                  │   │
│  │   │                 │  │                 │  │                 │                  │   │
│  │   │ • Glue Jobs     │  │ • Email         │  │ • Threshold     │                  │   │
│  │   │ • ECS Tasks     │  │   Notifications │  │   Monitoring    │                  │   │
│  │   │ • Kafka Health  │  │                 │  │                 │                  │   │
│  │   └─────────────────┘  └─────────────────┘  └─────────────────┘                  │   │
│  └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                        │
└────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              LOCAL DEVELOPMENT (Docker)                                  │
│                                                                                          │
│   ┌─────────────┐      ┌─────────────┐      ┌─────────────┐      ┌─────────────┐        │
│   │  PostgreSQL │      │    Kafka    │      │  Debezium   │      │  Kafka UI   │        │
│   │  (Port 5432)│◀────▶│ (Port 9092) │◀────▶│ (Port 8083) │      │ (Port 8081) │        │
│   │             │  WAL  │             │ JSON │             │      │             │        │
│   │ • cdc_demo  │──────▶│ • KRaft     │──────▶│ • Connector │      │ • Monitoring│        │
│   │ • Logical   │      │ • Internal  │      │ • Slot      │      │ • Topics    │        │
│   │   Replica   │      │ • External  │      │             │      │ • Messages  │        │
│   └─────────────┘      └─────────────┘      └─────────────┘      └─────────────┘        │
│                                                                                          │
│   Data flows to AWS S3 (not local storage)                                              │
└─────────────────────────────────────────────────────────────────────────────────────────┘
