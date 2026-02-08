# Airflow Module Variables
variable "project_name" {
  type        = string
  description = "Project name"
}

variable "environment" {
  type        = string
  description = "Environment name"
}

variable "vpc_id" {
  type        = string
  description = "VPC ID"
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Private subnet IDs"
}

variable "public_subnet_ids" {
  type        = list(string)
  description = "Public subnet IDs"
}

variable "s3_bucket_name" {
  type        = string
  description = "S3 bucket for DAGs and logs"
}

variable "aws_region" {
  type        = string
  description = "AWS region"
  default     = "ap-south-1"
}

# Airflow connection strings (use RDS + ElastiCache in production)
variable "airflow_db_conn" {
  type        = string
  description = "Airflow database connection string"
  default     = "postgresql://airflow:airflow@localhost:5432/airflow"
}

variable "celery_broker_url" {
  type        = string
  description = "Celery broker URL (use ElastiCache Redis in production)"
  default     = "redis://localhost:6379/0"
}

variable "celery_result_backend" {
  type        = string
  description = "Celery result backend"
  default     = "db+postgresql://airflow:airflow@localhost:5432/airflow"
}

variable "tags" {
  type = map(string)
  default = {
    Project     = "cdc-pipeline"
    Environment = "dev"
  }
}

