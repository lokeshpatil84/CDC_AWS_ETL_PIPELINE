"""
Silver to Gold Glue Job
Business aggregations on S3 Silver → S3 Gold
Fits with: module.glue, module.s3
"""

import logging
import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql.functions import *
from pyspark.sql.window import Window

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("silver-to-gold")


class SilverToGold:
    def __init__(self, database: str, bucket: str):
        self.database = database
        self.bucket = bucket
        self.spark = self._init_glue()

    def _init_glue(self):
        args = getResolvedOptions(sys.argv, ["JOB_NAME"])

        sc = SparkContext()
        glueContext = GlueContext(sc)
        spark = glueContext.spark_session

        Job(glueContext).init(args["JOB_NAME"], args)

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

        spark.conf.set("spark.sql.adaptive.enabled", "true")
        spark.conf.set("spark.sql.adaptive.coalescePartitions.enabled", "true")

        return spark

    def table_exists(self, table: str) -> bool:
        try:
            self.spark.read.table(f"glue.{self.database}.{table}")
            return True
        except:
            return False

    def build_user_analytics(self):
        """RFM analysis on current user records"""
        logger.info("Building user analytics")

        if not self.table_exists("silver_users") or not self.table_exists(
            "silver_orders"
        ):
            logger.warning("Missing dependencies for user analytics")
            return

        # Read current records only
        users = self.spark.read.table(f"glue.{self.database}.silver_users").filter(
            "_is_current = true"
        )
        orders = self.spark.read.table(f"glue.{self.database}.silver_orders").filter(
            "_is_current = true"
        )

        # Calculate user order statistics
        user_stats = orders.groupBy("user_id").agg(
            count("*").alias("total_orders"),
            sum("total_amount").alias("total_spent"),
            avg("total_amount").alias("avg_order_value"),
            max("_valid_from").alias("last_order_date"),
            min("_valid_from").alias("first_order_date"),
        )

        # Build analytics
        result = users.join(
            user_stats, users["id"] == user_stats["user_id"], "left"
        ).select(
            users["id"].alias("user_id"),
            users["name"].alias("full_name"),
            users["email_domain"],
            date_format(users["_valid_from"], "yyyy-MM-dd").alias("registration_date"),
            coalesce(user_stats["total_orders"], lit(0)).alias("total_orders"),
            coalesce(user_stats["total_spent"], lit(0.0)).alias("total_spent"),
            coalesce(user_stats["avg_order_value"], lit(0.0)).alias("avg_order_value"),
            user_stats["last_order_date"],
            datediff(current_date(), user_stats["last_order_date"]).alias(
                "recency_days"
            ),
            # Customer segmentation
            when(coalesce(user_stats["total_spent"], lit(0.0)) > 1000, "VIP")
            .when(coalesce(user_stats["total_spent"], lit(0.0)) > 500, "Loyal")
            .when(coalesce(user_stats["total_orders"], lit(0)) > 5, "Frequent")
            .otherwise("New")
            .alias("segment"),
            current_timestamp().alias("refresh_date"),
        )

        # Create table if not exists
        self.spark.sql(f"""
            CREATE TABLE IF NOT EXISTS glue.{self.database}.gold_user_analytics (
                user_id BIGINT,
                full_name STRING,
                email_domain STRING,
                registration_date STRING,
                total_orders BIGINT,
                total_spent DOUBLE,
                avg_order_value DOUBLE,
                last_order_date TIMESTAMP,
                recency_days INT,
                segment STRING,
                refresh_date TIMESTAMP
            ) USING iceberg
            TBLPROPERTIES ('format-version'='2')
        """)

        # Write with replace (full rebuild for simplicity)
        # For incremental, use MERGE instead
        result.writeTo(f"glue.{self.database}.gold_user_analytics").replace()
        logger.info(f"User analytics: {result.count()} records")

    def build_product_analytics(self):
        """Product performance metrics"""
        logger.info("Building product analytics")

        if not self.table_exists("silver_products") or not self.table_exists(
            "silver_orders"
        ):
            logger.warning("Missing dependencies for product analytics")
            return

        products = self.spark.read.table(
            f"glue.{self.database}.silver_products"
        ).filter("_is_current = true")
        orders = self.spark.read.table(f"glue.{self.database}.silver_orders").filter(
            "_is_current = true"
        )

        # Overall product stats
        product_stats = orders.groupBy("product_id").agg(
            count("*").alias("total_orders"),
            sum("total_amount").alias("total_revenue"),
            countDistinct("user_id").alias("unique_customers"),
        )

        # Last 30 days stats
        recent_stats = (
            orders.filter(datediff(current_date(), col("_valid_from")) <= 30)
            .groupBy("product_id")
            .agg(sum("total_amount").alias("revenue_last_30d"))
        )

        result = (
            products.join(
                product_stats, products["id"] == product_stats["product_id"], "left"
            )
            .join(recent_stats, products["id"] == recent_stats["product_id"], "left")
            .select(
                products["id"].alias("product_id"),
                products["name"].alias("product_name"),
                products["category"],
                products["price"],
                coalesce(product_stats["total_orders"], lit(0)).alias("total_orders"),
                coalesce(product_stats["total_revenue"], lit(0.0)).alias(
                    "total_revenue"
                ),
                coalesce(product_stats["unique_customers"], lit(0)).alias(
                    "unique_customers"
                ),
                coalesce(recent_stats["revenue_last_30d"], lit(0.0)).alias(
                    "revenue_last_30d"
                ),
                # Performance tier
                when(coalesce(product_stats["total_revenue"], lit(0.0)) > 10000, "Star")
                .when(coalesce(product_stats["total_revenue"], lit(0.0)) > 5000, "Good")
                .when(
                    coalesce(product_stats["total_revenue"], lit(0.0)) > 1000, "Average"
                )
                .otherwise("Low")
                .alias("performance_tier"),
                current_timestamp().alias("refresh_date"),
            )
        )

        self.spark.sql(f"""
            CREATE TABLE IF NOT EXISTS glue.{self.database}.gold_product_analytics (
                product_id BIGINT,
                product_name STRING,
                category STRING,
                price DOUBLE,
                total_orders BIGINT,
                total_revenue DOUBLE,
                unique_customers BIGINT,
                revenue_last_30d DOUBLE,
                performance_tier STRING,
                refresh_date TIMESTAMP
            ) USING iceberg
            TBLPROPERTIES ('format-version'='2')
        """)

        result.writeTo(f"glue.{self.database}.gold_product_analytics").replace()
        logger.info(f"Product analytics: {result.count()} records")

    def build_sales_summary(self):
        """Daily sales aggregations"""
        logger.info("Building sales summary")

        if not self.table_exists("silver_orders"):
            logger.warning("Missing dependencies for sales summary")
            return

        orders = self.spark.read.table(f"glue.{self.database}.silver_orders").filter(
            "_is_current = true"
        )

        # Extract date from timestamp
        orders = orders.withColumn(
            "order_date", date_format(col("_valid_from"), "yyyy-MM-dd")
        )

        # Daily aggregates
        daily = orders.groupBy("order_date").agg(
            count("*").alias("total_orders"),
            sum("total_amount").alias("total_revenue"),
            avg("total_amount").alias("avg_order_value"),
            countDistinct("user_id").alias("unique_customers"),
        )

        # Top product per day
        product_daily = orders.groupBy("order_date", "product_id").agg(
            sum("total_amount").alias("product_revenue")
        )

        top_product = (
            product_daily.withColumn(
                "rank",
                row_number().over(
                    Window.partitionBy("order_date").orderBy(
                        col("product_revenue").desc()
                    )
                ),
            )
            .filter("rank = 1")
            .select("order_date", col("product_id").alias("top_product_id"))
        )

        result = daily.join(top_product, "order_date", "left").select(
            col("order_date").alias("date_key"),
            col("total_orders"),
            col("total_revenue"),
            col("avg_order_value"),
            col("unique_customers"),
            coalesce(col("top_product_id"), lit(0)).alias("top_product_id"),
            current_timestamp().alias("refresh_date"),
        )

        self.spark.sql(f"""
            CREATE TABLE IF NOT EXISTS glue.{self.database}.gold_sales_summary (
                date_key STRING,
                total_orders BIGINT,
                total_revenue DOUBLE,
                avg_order_value DOUBLE,
                unique_customers BIGINT,
                top_product_id BIGINT,
                refresh_date TIMESTAMP
            ) USING iceberg
            PARTITIONED BY (days(refresh_date))
            TBLPROPERTIES ('format-version'='2')
        """)

        result.writeTo(f"glue.{self.database}.gold_sales_summary").replace()
        logger.info(f"Sales summary: {result.count()} records")

    def run(self):
        """Execute all Gold layer builds"""
        logger.info("=" * 70)
        logger.info("SILVER TO GOLD: Business Aggregations")
        logger.info(f"Database: {self.database}")
        logger.info(f"Bucket: s3://{self.bucket}")
        logger.info("=" * 70)

        self.build_user_analytics()
        self.build_product_analytics()
        self.build_sales_summary()

        # Final stats
        logger.info("-" * 70)
        for table in [
            "gold_user_analytics",
            "gold_product_analytics",
            "gold_sales_summary",
        ]:
            try:
                count = self.spark.sql(
                    f"SELECT COUNT(*) FROM glue.{self.database}.{table}"  # nosec B608
                ).collect()[0][0]
                logger.info(f"{table}: {count} records")
            except:
                pass
        logger.info("=" * 70)


if __name__ == "__main__":
    args = getResolvedOptions(sys.argv, ["JOB_NAME", "DATABASE_NAME", "S3_BUCKET"])
    processor = SilverToGold(args["DATABASE_NAME"], args["S3_BUCKET"])
    processor.run()
