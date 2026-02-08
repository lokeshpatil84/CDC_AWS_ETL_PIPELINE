"""
Bronze to Silver Glue Job
Reads from S3 Bronze, applies SCD Type 2, writes to S3 Silver
Fits with: module.glue (Glue jobs), module.s3 (bucket)
"""

import sys
import logging
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql.functions import *
from pyspark.sql.window import Window


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("bronze-to-silver")


class BronzeToSilver:
    TABLES = ["users", "products", "orders"]

    # Schema definitions for JSON parsing
    TABLE_SCHEMAS = {
        "users": {
            "columns": ["id", "name", "email", "created_at", "updated_at"],
            "types": {"id": "long", "created_at": "long", "updated_at": "long"},
            "transforms": {"email_domain": regexp_extract(col("email"), "@(.+)$", 1)},
        },
        "products": {
            "columns": ["id", "name", "price", "category", "created_at", "updated_at"],
            "types": {
                "id": "long",
                "price": "double",
                "created_at": "long",
                "updated_at": "long",
            },
            "transforms": {
                "price_category": when(col("price") < 50, "Low")
                .when(col("price") < 200, "Medium")
                .otherwise("High")
            },
        },
        "orders": {
            "columns": [
                "id",
                "user_id",
                "product_id",
                "quantity",
                "total_amount",
                "status",
                "created_at",
                "updated_at",
            ],
            "types": {
                "id": "long",
                "user_id": "long",
                "product_id": "long",
                "quantity": "int",
                "total_amount": "double",
                "created_at": "long",
                "updated_at": "long",
            },
            "transforms": {
                "order_value_category": when(col("total_amount") < 100, "Small")
                .when(col("total_amount") < 500, "Medium")
                .otherwise("Large")
            },
        },
    }

    def __init__(self, database: str, bucket: str):
        self.database = database
        self.bucket = bucket
        self.spark = self._init_glue()

    def _init_glue(self):
        """Initialize Glue with S3 + Iceberg"""
        args = getResolvedOptions(sys.argv, ["JOB_NAME"])

        sc = SparkContext()
        glueContext = GlueContext(sc)
        spark = glueContext.spark_session

        Job(glueContext).init(args["JOB_NAME"], args)

        # Glue Catalog with S3
        spark.conf.set(
            "spark.sql.catalog.glue", "org.apache.iceberg.spark.SparkCatalog"
        )
        spark.conf.set(
            "spark.sql.catalog.glue.catalog-impl",
            "org.apache.iceberg.aws.glue.GlueCatalog",
        )
        spark.conf.set(
            "spark.sql.catalog.glue.warehouse", f"s3://{self.bucket}/iceberg/"
        )
        spark.conf.set(
            "spark.sql.catalog.glue.io-impl", "org.apache.iceberg.aws.s3.S3FileIO"
        )

        # S3 optimizations
        spark.conf.set("spark.sql.adaptive.enabled", "true")
        spark.conf.set("spark.sql.adaptive.coalescePartitions.enabled", "true")
        spark.conf.set("spark.sql.adaptive.skewJoin.enabled", "true")

        # Iceberg specific
        spark.conf.set("spark.sql.catalog.glue.write_metadata_compression", "gzip")

        return spark

    def table_exists(self, table: str) -> bool:
        try:
            self.spark.read.table(f"glue.{self.database}.{table}")
            return True
        except:
            return False

    def create_silver_table(self, table: str):
        """Create Silver table with SCD Type 2 columns"""
        base_schemas = {
            "users": "id BIGINT, name STRING, email STRING, email_domain STRING, is_active BOOLEAN",
            "products": "id BIGINT, name STRING, price DOUBLE, category STRING, price_category STRING, is_active BOOLEAN",
            "orders": "id BIGINT, user_id BIGINT, product_id BIGINT, quantity INT, total_amount DOUBLE, status STRING, order_value_category STRING, is_active BOOLEAN",
        }

        audit_cols = """
            , operation STRING
            , source_ts_ms BIGINT
            , processed_at TIMESTAMP
            , kafka_partition INT
            , kafka_offset BIGINT
            , pg_lsn BIGINT
            , _valid_from TIMESTAMP
            , _valid_to TIMESTAMP
            , _is_current BOOLEAN
            , _hash STRING
            , _cdc_order_lsn BIGINT
        """

        full_table = f"glue.{self.database}.silver_{table}"

        # Check if table exists
        if not self.table_exists(f"silver_{table}"):
            logger.info(f"Creating Silver table: {full_table}")
            self.spark.sql(
                f"""
                CREATE TABLE IF NOT EXISTS {full_table} (
                    {base_schemas[table]}
                    {audit_cols}
                ) USING iceberg
                PARTITIONED BY (days(_valid_from))
                TBLPROPERTIES (
                    'format-version'='2',
                    'write_compression'='ZSTD',
                    'write.target-file-size-bytes'='134217728',
                    'write.metadata.compression-codec'='gzip'
                )
            """
            )
        else:
            logger.info(f"Silver table exists: {full_table}")

    def read_bronze_incremental(self, table: str):
        """Read new records using watermark from Silver"""
        bronze_table = f"glue.{self.database}.bronze_cdc_events"

        if not self.table_exists("bronze_cdc_events"):
            logger.warning("Bronze table not found")
            return None

        # Read Bronze for this table only
        bronze_df = self.spark.read.table(bronze_table).filter(
            f"source_table = '{table}'"
        )

        # Get watermark from Silver (max source_ts_ms with 1hr lookback)
        silver_table = f"glue.{self.database}.silver_{table}"
        watermark = None

        if self.table_exists(f"silver_{table}"):
            try:
                watermark_df = self.spark.sql(
                    f"SELECT MAX(source_ts_ms) as watermark FROM {silver_table}"
                )
                watermark_row = watermark_df.collect()
                if watermark_row and watermark_row[0][0]:
                    watermark = watermark_row[0][0]
                    # 1 hour lookback for late arrivals
                    lookback = watermark - 3600000
                    bronze_df = bronze_df.filter(col("source_ts_ms") > lookback)
                    logger.info(
                        f"Incremental load: source_ts_ms > {lookback} (watermark: {watermark})"
                    )
            except Exception as e:
                logger.warning(f"Could not get watermark, doing full load: {e}")

        # Check if empty
        count = bronze_df.count()
        if count == 0:
            logger.info(f"No new data for {table}")
            return None

        logger.info(f"Read {count} records from Bronze for {table}")
        return bronze_df

    def parse_and_transform(self, df, table: str):
        """Parse JSON and apply business transformations"""
        config = self.TABLE_SCHEMAS[table]

        # Select data based on operation (use before for deletes, after for inserts/updates)
        data_col = when(col("operation") == "d", col("before_json")).otherwise(
            col("after_json")
        )

        # Get sample for schema inference (handle nulls)
        sample_rows = (
            df.filter(data_col.isNotNull()).select(data_col).limit(10).collect()
        )
        if not sample_rows:
            logger.warning(f"No valid data found for {table}")
            return None

        # Infer schema from first valid row
        sample_json = sample_rows[0][0]
        json_schema = self.spark.read.json(
            self.spark.sparkContext.parallelize([sample_json])
        ).schema

        parsed = df.withColumn("data", from_json(data_col, json_schema))

        # Build select expressions
        selects = []
        for col_name in config["columns"]:
            cast_type = config["types"].get(col_name, "string")
            selects.append(col(f"data.{col_name}").cast(cast_type).alias(col_name))

        # Add computed columns
        for new_col, expr in config["transforms"].items():
            selects.append(expr.alias(new_col))

        # Add audit columns
        selects.extend(
            [
                when(col("operation") == "d", False).otherwise(True).alias("is_active"),
                col("operation"),
                col("source_ts_ms"),
                col("processed_at"),
                col("kafka_partition"),
                col("kafka_offset"),
                col("pg_lsn"),
            ]
        )

        result = parsed.select(*selects)

        # Deduplicate: keep latest per ID using LSN ordering
        window = Window.partitionBy("id").orderBy(
            col("pg_lsn").desc(), col("source_ts_ms").desc(), col("kafka_offset").desc()
        )

        deduped = (
            result.withColumn("row_num", row_number().over(window))
            .filter("row_num = 1")
            .drop("row_num")
        )

        return deduped

    def generate_hash(self, df, table: str):
        """Generate SHA-256 hash for change detection (better than MD5)"""
        config = self.TABLE_SCHEMAS[table]
        business_cols = (
            config["columns"] + list(config["transforms"].keys()) + ["is_active"]
        )

        # Build concatenation with null handling
        concat_exprs = [
            coalesce(col(c).cast("string"), lit("NULL")) for c in business_cols
        ]
        concat_str = concat_ws("||", *concat_exprs)

        return df.withColumn("_hash", sha2(concat_str, 256))

    def merge_scd2(self, df, table: str):
        """Atomic MERGE operation for SCD Type 2"""
        target = f"glue.{self.database}.silver_{table}"
        staging = f"staging_{table}_{int(time.time())}"

        # Generate hash and add SCD columns
        df_hashed = self.generate_hash(df, table)

        # Add SCD Type 2 tracking columns
        current_time = current_timestamp()
        staged_df = df_hashed.select(
            "*",
            current_time.alias("_valid_from"),
            lit(None).cast("timestamp").alias("_valid_to"),
            lit(True).alias("_is_current"),
            col("pg_lsn").alias("_cdc_order_lsn"),
        )

        staged_df.createOrReplaceTempView(staging)

        # Get column lists for INSERT
        config = self.TABLE_SCHEMAS[table]
        base_cols = (
            config["columns"]
            + list(config["transforms"].keys())
            + [
                "is_active",
                "operation",
                "source_ts_ms",
                "processed_at",
                "kafka_partition",
                "kafka_offset",
                "pg_lsn",
                "_hash",
            ]
        )
        scd_cols = ["_valid_from", "_valid_to", "_is_current", "_cdc_order_lsn"]
        all_cols = base_cols + scd_cols

        cols_str = ", ".join(all_cols)

        # Single atomic MERGE operation
        merge_sql = f"""
            MERGE INTO {target} AS tgt
            USING {staging} AS src
            ON tgt.id = src.id AND tgt._is_current = true
            
            -- Handle deletes: close current record
            WHEN MATCHED AND src.operation = 'd' THEN
                UPDATE SET 
                    is_active = false,
                    _valid_to = current_timestamp(),
                    _is_current = false
            
            -- Handle updates: close old record if changed
            WHEN MATCHED AND src._hash != tgt._hash AND src.source_ts_ms > tgt.source_ts_ms THEN
                UPDATE SET 
                    _valid_to = current_timestamp(),
                    _is_current = false
            
            -- Insert new record for inserts and updates (where hash changed or new record)
            WHEN NOT MATCHED THEN
                INSERT ({cols_str})
                VALUES ({cols_str})
        """

        self.spark.sql(merge_sql)

        # Insert new versions for updated records (where we closed the old one)
        insert_sql = f"""
            INSERT INTO {target}
            SELECT {cols_str}
            FROM {staging} src
            WHERE src.operation != 'd'
            AND EXISTS (
                SELECT 1 FROM {target} tgt2 
                WHERE tgt2.id = src.id 
                AND tgt2._is_current = false
                AND tgt2._hash != src._hash
                AND tgt2._valid_to = (
                    SELECT MAX(_valid_to) FROM {target} tgt3 
                    WHERE tgt3.id = src.id AND tgt3._is_current = false
                )
            )
            AND NOT EXISTS (
                SELECT 1 FROM {target} tgt4 
                WHERE tgt4.id = src.id AND tgt4._is_current = true AND tgt4._hash = src._hash
            )
        """

        self.spark.sql(insert_sql)

        logger.info(f"SCD2 MERGE completed for {table}")

    def process_table(self, table: str):
        """Process single table end-to-end"""
        logger.info(f"Processing table: {table}")

        # Ensure table exists
        self.create_silver_table(table)

        # Read incremental data
        df = self.read_bronze_incremental(table)
        if df is None:
            return

        # Parse and transform
        transformed = self.parse_and_transform(df, table)
        if transformed is None:
            return

        # Apply SCD Type 2 merge
        self.merge_scd2(transformed, table)

        # Log stats
        try:
            total = self.spark.sql(
                f"SELECT COUNT(*) FROM glue.{self.database}.silver_{table}"
            ).collect()[0][0]
            current = self.spark.sql(
                f"SELECT COUNT(*) FROM glue.{self.database}.silver_{table} WHERE _is_current = true"
            ).collect()[0][0]
            logger.info(f"Silver {table}: Total={total}, Current={current}")
        except Exception as e:
            logger.warning(f"Could not get stats: {e}")

    def run(self):
        """Main execution"""
        import time

        logger.info("=" * 70)
        logger.info("BRONZE TO SILVER: SCD Type 2 Processing")
        logger.info(f"Database: {self.database}")
        logger.info(f"Bucket: s3://{self.bucket}")
        logger.info("=" * 70)

        for table in self.TABLES:
            try:
                self.process_table(table)
            except Exception as e:
                logger.error(f"Failed processing {table}: {e}")
                raise

        logger.info("Silver processing completed successfully")


if __name__ == "__main__":
    args = getResolvedOptions(sys.argv, ["JOB_NAME", "DATABASE_NAME", "S3_BUCKET"])
    processor = BronzeToSilver(args["DATABASE_NAME"], args["S3_BUCKET"])
    processor.run()
