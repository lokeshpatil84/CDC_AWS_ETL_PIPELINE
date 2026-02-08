resource "aws_iam_role" "glue_role" {
  name = "${var.project_name}-${var.environment}-glue-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "glue.amazonaws.com"
        }
      }
    ]
  })

  lifecycle { create_before_destroy = true }

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-glue-role"
  })
}

resource "aws_iam_role_policy_attachment" "glue_service" {
  role       = aws_iam_role.glue_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

resource "aws_iam_policy" "glue_s3_policy" {
  name = "${var.project_name}-${var.environment}-glue-s3-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Effect   = "Allow"
        Resource = ["arn:aws:s3:::${var.s3_bucket_name}", "arn:aws:s3:::${var.s3_bucket_name}/*"]
      },
      {
        Action   = ["s3:ListBucket"]
        Effect   = "Allow"
        Resource = "arn:aws:s3:::${var.s3_bucket_name}"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "glue_s3" {
  role       = aws_iam_role.glue_role.name
  policy_arn = aws_iam_policy.glue_s3_policy.arn
}

resource "aws_iam_policy" "glue_logs_policy" {
  name = "${var.project_name}-${var.environment}-glue-logs-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Effect   = "Allow"
        Resource = "arn:aws:logs:*:*:log-group:/aws/glue/*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "glue_logs" {
  role       = aws_iam_role.glue_role.name
  policy_arn = aws_iam_policy.glue_logs_policy.arn
}

resource "aws_iam_policy" "glue_catalog_policy" {
  name = "${var.project_name}-${var.environment}-glue-catalog-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["glue:GetDatabase", "glue:CreateDatabase", "glue:GetTable",
          "glue:CreateTable", "glue:UpdateTable", "glue:GetPartitions",
        "glue:CreatePartition", "glue:BatchCreatePartition"]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "glue_catalog" {
  role       = aws_iam_role.glue_role.name
  policy_arn = aws_iam_policy.glue_catalog_policy.arn
}

# Kafka to Bronze Job - Streaming ingestion from Kafka to S3 Bronze
resource "aws_glue_job" "kafka_to_bronze" {
  name         = "${var.project_name}-${var.environment}-kafka-to-bronze"
  role_arn     = aws_iam_role.glue_role.arn
  glue_version = "4.0"

  command {
    python_version  = "3"
    script_location = "s3://${var.s3_bucket_name}/scripts/kafka_to_bronze.py"
  }

  execution_property { max_concurrent_runs = 1 }

  default_arguments = {
    "--JOB_NAME"                         = "${var.project_name}-${var.environment}-kafka-to-bronze"
    "--DATABASE_NAME"                    = "cdc_demo"
    "--S3_BUCKET"                        = var.s3_bucket_name
    "--KAFKA_BOOTSTRAP_SERVERS"          = var.kafka_bootstrap_servers
    "--REGION"                           = var.aws_region
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = ""
    "--additional-python-modules"        = "pyiceberg==0.5.1"
    "--datalake-formats"                 = "iceberg"
  }

  worker_type       = var.worker_type
  number_of_workers = var.number_of_workers
  timeout           = var.glue_job_timeout

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-kafka-to-bronze"
  })
}

# Bronze to Silver Job - SCD Type 2 transformations
resource "aws_glue_job" "bronze_to_silver" {
  name         = "${var.project_name}-${var.environment}-bronze-to-silver"
  role_arn     = aws_iam_role.glue_role.arn
  glue_version = "4.0"

  command {
    python_version  = "3"
    script_location = "s3://${var.s3_bucket_name}/scripts/bronze_to_silver.py"
  }

  execution_property { max_concurrent_runs = 1 }

  default_arguments = {
    "--JOB_NAME"                         = "${var.project_name}-${var.environment}-bronze-to-silver"
    "--DATABASE_NAME"                    = "cdc_demo"
    "--S3_BUCKET"                        = var.s3_bucket_name
    "--REGION"                           = var.aws_region
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = ""
    "--additional-python-modules"        = "pyiceberg==0.5.1"
    "--datalake-formats"                 = "iceberg"
  }

  worker_type       = var.worker_type
  number_of_workers = var.number_of_workers
  timeout           = var.glue_job_timeout

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-bronze-to-silver"
  })
}

# Silver to Gold Job - Business aggregations
resource "aws_glue_job" "silver_to_gold" {
  name         = "${var.project_name}-${var.environment}-silver-to-gold"
  role_arn     = aws_iam_role.glue_role.arn
  glue_version = "4.0"

  command {
    python_version  = "3"
    script_location = "s3://${var.s3_bucket_name}/scripts/silver_to_gold.py"
  }

  execution_property { max_concurrent_runs = 1 }

  default_arguments = {
    "--JOB_NAME"                         = "${var.project_name}-${var.environment}-silver-to-gold"
    "--DATABASE_NAME"                    = "cdc_demo"
    "--S3_BUCKET"                        = var.s3_bucket_name
    "--REGION"                           = var.aws_region
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = ""
    "--additional-python-modules"        = "pyiceberg==0.5.1"
    "--datalake-formats"                 = "iceberg"
  }

  worker_type       = var.worker_type
  number_of_workers = var.number_of_workers
  timeout           = var.glue_job_timeout

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-silver-to-gold"
  })
}

resource "aws_glue_catalog_database" "data_lake" {
  name        = "${var.project_name}_${var.environment}_data_lake"
  description = "CDC Pipeline Data Lake Database"

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-glue-db"
  })
}

resource "aws_cloudwatch_log_group" "glue" {
  name              = "/aws/glue/${var.project_name}-${var.environment}"
  retention_in_days = 30

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-glue-logs"
  })
}

# =========================================================
# Auto-upload Glue Scripts to S3
# =========================================================

resource "null_resource" "upload_glue_scripts" {
  triggers = {
    # Recreate when any glue script changes
    kafka_to_bronze_hash  = fileexists("${path.module}/../../glue/kafka_to_bronze.py") ? filesha256("${path.module}/../../glue/kafka_to_bronze.py") : "none"
    bronze_to_silver_hash = fileexists("${path.module}/../../glue/bronze_to_silver.py") ? filesha256("${path.module}/../../glue/bronze_to_silver.py") : "none"
    silver_to_gold_hash   = fileexists("${path.module}/../../glue/silver_to_gold.py") ? filesha256("${path.module}/../../glue/silver_to_gold.py") : "none"
  }

  provisioner "local-exec" {
    command = <<EOT
echo "Uploading Glue scripts to S3..."
aws s3 cp ../glue/ s3://${var.s3_bucket_name}/scripts/ --recursive --region ${var.aws_region}
echo "Scripts uploaded successfully!"
EOT

    working_dir = "${path.module}/../.."
  }
}

