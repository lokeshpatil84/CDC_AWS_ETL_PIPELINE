# Terraform Backend Bootstrap - Production Grade
# This Terraform creates the backend infrastructure needed for main Terraform
# Run this FIRST before any other Terraform operations
# This file should NOT be managed by Terraform itself

terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ============================================
# S3 Bucket for Terraform State (Backend)
# ============================================
resource "aws_s3_bucket" "terraform_state" {
  bucket = var.bucket_name

  # Prevent accidental deletion
  lifecycle {
    prevent_destroy = false
  }

  tags = merge(var.tags, {
    Name        = "${var.project_name}-tfstate-${var.environment}"
    Description = "Terraform state backend for ${var.project_name}"
    ManagedBy   = "terraform-bootstrap"
    Environment = var.environment
  })
}

# Enable Versioning for state history/rollback
resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Enable Server-Side Encryption (AES256)
resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Block all public access (security best practice)
resource "aws_s3_bucket_public_access_block" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ============================================
# DynamoDB Table for State Locking
# ============================================
resource "aws_dynamodb_table" "terraform_lock" {
  name         = var.dynamodb_table_name
  billing_mode = "PAY_PER_REQUEST" # On-demand capacity
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  # Enable server-side encryption
  server_side_encryption {
    enabled = true
  }

  tags = merge(var.tags, {
    Name        = "${var.project_name}-terraform-lock-${var.environment}"
    Description = "Terraform state locking for ${var.project_name}"
    ManagedBy   = "terraform-bootstrap"
    Environment = var.environment
  })
}

