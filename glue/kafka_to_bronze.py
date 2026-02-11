"""
Kafka (Self-Managed on EC2) -> S3 Bronze (Iceberg)
Fits with: module.kafka (EC2 instance), module.s3 (bucket), module.ecs (Debezium)
"""

import logging
import os
import sys
from typing import Dict, List

from awsglue.utils import getResolvedOptions
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import *
from pyspark.sql.types import *

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("kafka-to-bronze")


class KafkaToBronze:
    TOPICS = ["cdc.db.users", "cdc.db.products", "cdc.db.orders"]

    def __init__(self):
        # Get arguments from Glue job parameters
        args = getResolvedOptions(sys.argv, [
            "S3_BUCKET",
            "KAFKA_BROKERS",
            "REGION",
            "DATABASE_NAME"
        ])
        
        # From Terraform environment
        self.aws_region = args.get("REGION", "ap-south-1")
        self.s3_bucket = args["S3_BUCKET"]  # From module.s3.data_bucket_name
        self.database = args.get("DATABASE_NAME", "cdc_pipeline")

        # Self-managed Kafka on EC2 (from module.kafka)
        self.kafka_brokers = args["KAFKA_BROKERS"]  # kafka-internal:9092
        self.kafka_security_protocol = os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")

        # For SASL/SSL if enabled
        self.kafka_username = os.getenv("KAFKA_USERNAME")
        self.kafka_password = os.getenv("KAFKA_PASSWORD")

        # Paths
        self.warehouse_path = f"s3://{self.s3_bucket}/iceberg/"
        self.checkpoint_path = f"s3://{self.s3_bucket}/checkpoints/bronze/"
        self.dlq_path = f"s3://{self.s3_bucket}/dlq/bronze/"

        self.spark = self._init_spark()

    def _init_spark(self) -> SparkSession:
        """Initialize Spark with Glue Catalog + S3 + Iceberg"""

        builder = (
            SparkSession.builder.appName("kafka-to-bronze")
            # Iceberg + Glue Catalog
            .config(
                "spark.sql.extensions",
                "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
            )
            .config("spark.sql.catalog.glue", "org.apache.iceberg.spark.SparkCatalog")
            .config(
                "spark.sql.catalog.glue.catalog-impl",
                "org.apache.iceberg.aws.glue.GlueCatalog",
            )
            .config("spark.sql.catalog.glue.warehouse", self.warehouse_path)
            .config(
                "spark.sql.catalog.glue.io-impl", "org.apache.iceberg.aws.s3.S3FileIO"
            )
            # S3 Configuration (IAM Role from ECS task or Glue job)
            .config(
                "spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem"
            )
            .config(
                "spark.hadoop.fs.s3a.aws.credentials.provider",
                "com.amazonaws.auth.DefaultAWSCredentialsProviderChain",
            )
            # Iceberg optimizations
            .config("spark.sql.catalog.glue.commit.retry.num-retries", "10")
            .config("spark.sql.catalog.glue.commit.retry.min-wait-ms", "100")
            .config("spark.sql.catalog.glue.commit.retry.max-wait-ms", "30000")
            # Streaming configs
            .config("spark.sql.streaming.metricsEnabled", "true")
            .config("spark.sql.adaptive.enabled", "true")
            .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
        )

        spark = builder.getOrCreate()
        spark.sparkContext.setLogLevel("WARN")

        # Create database if not exists
        spark.sql(f"CREATE DATABASE IF NOT EXISTS glue.{self.database}")

        return spark

    def _get_kafka_options(self) -> Dict[str, str]:
        """Build Kafka connection options for self-managed Kafka"""
        options = {
            "kafka.bootstrap.servers": self.kafka_brokers,
            "subscribe": ",".join(self.TOPICS),
            "startingOffsets": "earliest",
            "failOnDataLoss": "false",
            "maxOffsetsPerTrigger": "50000",  # Batch size control
            "kafka.security.protocol": self.kafka_security_protocol,
        }

        # Add SASL if credentials provided
        if self.kafka_username and self.kafka_password:
            options.update(
                {
                    "kafka.sasl.mechanism": "SCRAM-SHA-256",
                    "kafka.sasl.jaas.config": f"org.apache.kafka.common.security.scram.ScramLoginModule required "
                    f'username="{self.kafka_username}" '
                    f'password="{self.kafka_password}";',
                }
            )

        return options

    def _cdc_schema(self) -> StructType:
        """CDC envelope schema - Debezium format"""
        return StructType(
            [
                StructField("before", StringType(), True),
                StructField("after", StringType(), True),
                StructField("op", StringType(), True),  # c=create, u=update, d=delete
                StructField("ts_ms", LongType(), True),  # Source timestamp
                StructField(
                    "source",
                    StructType(
                        [
                            StructField("db", StringType(), True),
                            StructField("schema", StringType(), True),
                            StructField("table", StringType(), True),
                            StructField("lsn", LongType(), True),  # PostgreSQL LSN
                            StructField("txId", LongType(), True),
                        ]
                    ),
                    True,
                ),
            ]
        )

    def read_kafka(self) -> DataFrame:
        """Read from self-managed Kafka cluster on EC2"""
        logger.info(f"Connecting to Kafka: {self.kafka_brokers}")
        logger.info(f"Topics: {self.TOPICS}")

        kafka_options = self._get_kafka_options()

        return self.spark.readStream.format("kafka").options(**kafka_options).load()

    def parse_events(self, kafka_df: DataFrame) -> DataFrame:
        """Parse Debezium CDC events"""
        parsed = kafka_df.select(
            col("topic"),
            col("partition").cast("int").alias("kafka_partition"),
            col("offset").cast("long").alias("kafka_offset"),
            col("timestamp").alias("kafka_timestamp"),
            col("key").cast("string").alias("record_key"),
            col("value").cast("string").alias("raw_value"),
            from_json(col("value").cast("string"), self._cdc_schema()).alias("cdc"),
        )

        return parsed.select(
            col("topic"),
            col("kafka_partition"),
            col("kafka_offset"),
            col("kafka_timestamp"),
            col("record_key"),
            col("raw_value"),
            col("cdc.op").alias("operation"),
            col("cdc.before").alias("before_json"),
            col("cdc.after").alias("after_json"),
            col("cdc.source.db").alias("source_db"),
            col("cdc.source.schema").alias("source_schema"),
            col("cdc.source.table").alias("source_table"),
            col("cdc.source.lsn").alias("pg_lsn"),
            col("cdc.source.txId").alias("pg_tx_id"),
            col("cdc.ts_ms").alias("source_ts_ms"),
            current_timestamp().alias("processed_at"),
            # Deduplication key
            concat_ws(
                "-", col("topic"), col("kafka_partition"), col("kafka_offset")
            ).alias("event_id"),
            # CDC ordering (LSN priority)
            col("cdc.source.lsn").alias("_cdc_order_lsn"),
        )

    def validate_events(self, df: DataFrame) -> tuple:
        """Validate and split good/bad records"""
        bad_condition = (
            col("operation").isNull()
            | col("source_table").isNull()
            | ~col("operation").isin("c", "u", "d")
            | ((col("after_json").isNull()) & (col("before_json").isNull()))
        )

        bad_df = (
            df.filter(bad_condition)
            .withColumn(
                "error_type",
                when(col("operation").isNull(), "NULL_OPERATION")
                .when(~col("operation").isin("c", "u", "d"), "INVALID_OPERATION")
                .when(col("source_table").isNull(), "NULL_TABLE")
                .when(
                    (col("after_json").isNull()) & (col("before_json").isNull()),
                    "EMPTY_PAYLOAD",
                )
                .otherwise("UNKNOWN"),
            )
            .withColumn("dlq_timestamp", current_timestamp())
        )

        good_df = df.filter(~bad_condition)

        return good_df, bad_df

    def ensure_bronze_table(self):
        """Create Bronze Iceberg table with partitioning"""
        full_table = f"glue.{self.database}.bronze_cdc_events"

        try:
            self.spark.read.table(full_table)
            logger.info(f"Bronze table exists: {full_table}")
        except Exception:
            logger.info(f"Creating Bronze table: {full_table}")
            self.spark.sql(f"""
                CREATE TABLE {full_table} (
                    topic STRING,
                    kafka_partition INT,
                    kafka_offset BIGINT,
                    kafka_timestamp TIMESTAMP,
                    record_key STRING,
                    raw_value STRING,
                    operation STRING,
                    before_json STRING,
                    after_json STRING,
                    source_db STRING,
                    source_schema STRING,
                    source_table STRING,
                    pg_lsn BIGINT,
                    pg_tx_id BIGINT,
                    source_ts_ms BIGINT,
                    processed_at TIMESTAMP,
                    event_id STRING,
                    _cdc_order_lsn BIGINT
                ) USING iceberg
                PARTITIONED BY (source_table, days(processed_at))
                TBLPROPERTIES (
                    'format-version'='2',
                    'write_compression'='ZSTD',
                    'write.metadata.compression-codec'='gzip',
                    'write.target-file-size-bytes'='134217728',
                    'commit.retry.num-retries'='10'
                )
            """)

    def write_bronze(self, df: DataFrame):
        """Write to Bronze with exactly-once guarantee"""
        self.ensure_bronze_table()
        target = f"glue.{self.database}.bronze_cdc_events"

        # Global deduplication using event_id
        deduped = df.dropDuplicates(["event_id"])

        return (
            deduped.writeStream.format("iceberg")
            .option("checkpointLocation", self.checkpoint_path)
            .outputMode("append")
            .trigger(processingTime="60 seconds")
            .option("fanout-enabled", "true")
            .queryName("bronze-writer")
            .toTable(target)
        )

    def write_dlq(self, bad_df: DataFrame):
        """Write bad records to S3 DLQ"""
        return (
            bad_df.select(
                "topic",
                "kafka_partition",
                "kafka_offset",
                "raw_value",
                "error_type",
                "processed_at",
                "dlq_timestamp",
            )
            .writeStream.format("json")
            .option("path", self.dlq_path)
            .option("checkpointLocation", f"{self.checkpoint_path}dlq/")
            .outputMode("append")
            .trigger(processingTime="120 seconds")
            .queryName("dlq-writer")
            .start()
        )

    def run(self):
        """Main execution"""
        logger.info("=" * 70)
        logger.info("KAFKA TO BRONZE: Self-Managed Kafka -> S3 Iceberg")
        logger.info(f"Kafka: {self.kafka_brokers}")
        logger.info(f"S3 Bucket: {self.s3_bucket}")
        logger.info(f"Glue DB: {self.database}")
        logger.info("=" * 70)

        raw = self.read_kafka()
        parsed = self.parse_events(raw)
        good, bad = self.validate_events(parsed)

        queries = []

        # Start DLQ first (less critical)
        if not bad.isStreaming:
            # If no bad data in test mode, skip
            pass
        else:
            q_dlq = self.write_dlq(bad)
            queries.append(q_dlq)

        # Start Bronze writer
        q_bronze = self.write_bronze(good)
        queries.append(q_bronze)

        logger.info(f"Started {len(queries)} streaming queries")

        try:
            self.spark.streams.awaitAnyTermination()
        except KeyboardInterrupt:
            logger.info("Shutdown signal received...")
            for q in queries:
                if q.isActive:
                    q.stop()
            logger.info("All streams stopped")


if __name__ == "__main__":
    job = KafkaToBronze()
    job.run()
