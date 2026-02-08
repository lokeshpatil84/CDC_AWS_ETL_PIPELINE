# Terraform Bootstrap Variables
# These variables configure the backend infrastructure

variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "ap-south-1"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "cdc-pipeline"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "bucket_name" {
  description = "S3 bucket name for Terraform state"
  type        = string
  default     = "cdc-pipeline-tfstate-dev"
}

variable "dynamodb_table_name" {
  description = "DynamoDB table name for Terraform state locking"
  type        = string
  default     = "cdc-pipeline-terraform-lock-dev"
}

variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default = {
    Project     = "cdc-pipeline"
    Environment = "dev"
    ManagedBy   = "terraform-bootstrap"
    Owner       = "data-engineering-team"
  }
}

# ============================================================================
# Idempotent Deployment Variables
# ============================================================================
# These variables help manage idempotent behavior for CI/CD pipelines

variable "force_recreate_table" {
  description = "Set to true to force recreation of DynamoDB table (use with caution)"
  type        = bool
  default     = false
  
  # WARNING: Setting this to true will delete and recreate the table
  # This will break any ongoing Terraform operations
  validation {
    condition     = var.force_recreate_table == false
    error_message = "WARNING: Set force_recreate_table to true only if you want to delete and recreate the DynamoDB table. This will break state locking!"
  }
}

variable "skip_table_creation" {
  description = "Set to true to skip DynamoDB table creation (use when table already exists outside Terraform)"
  type        = bool
  default     = false
}

