# Glue Module Variables
variable "project_name" {
  type        = string
  description = "Project name"
}

variable "environment" {
  type        = string
  description = "Environment name"
}

variable "s3_bucket_name" {
  type        = string
  description = "S3 bucket for data lake"
}

variable "worker_type" {
  type        = string
  default     = "G.1X"
  description = "Glue worker type"
}

variable "number_of_workers" {
  type        = number
  default     = 2
  description = "Number of workers"
}

variable "glue_job_timeout" {
  type        = number
  default     = 120
  description = "Job timeout in minutes"
}

variable "aws_region" {
  type        = string
  description = "AWS region"
  default     = "ap-south-1"
}

variable "kafka_bootstrap_servers" {
  type        = string
  description = "Kafka bootstrap servers (PLAINTEXT)"
  default     = ""
  sensitive   = true
}

variable "tags" {
  type = map(string)
  default = {
    Project     = "cdc-pipeline"
    Environment = "dev"
  }
}

