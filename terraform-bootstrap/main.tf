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

# S3 Bucket for Terraform State (Backend)
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

# DynamoDB Table for State Locking

# Check if DynamoDB table already exists (for idempotent deployments)
data "aws_dynamodb_table" "existing_lock" {
  name = var.dynamodb_table_name
  count = 1
  
  lifecycle {
    precondition {
      condition     = var.skip_table_creation != true || var.force_recreate_table == true
      error_message = "Cannot use skip_table_creation with existing table. Either remove skip_table_creation flag or set force_recreate_table=true to recreate."
    }
  }
}

# Create DynamoDB table only if it doesn't already exist
resource "aws_dynamodb_table" "terraform_lock" {
  count = (var.skip_table_creation == true || var.force_recreate_table == true) ? 0 : try(data.aws_dynamodb_table.existing_lock[0].name, "") == "" ? 1 : 0
  
  name         = var.dynamodb_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  server_side_encryption {
    enabled = true
  }

  tags = merge(var.tags, {
    Name        = "${var.project_name}-terraform-lock-${var.environment}"
    Description = "Terraform state locking for ${var.project_name}"
    ManagedBy   = "terraform-bootstrap"
    Environment = var.environment
  })
  
  lifecycle {
    prevent_destroy = false
    
    ignore_changes = [
      name,
      billing_mode,
      server_side_encryption,
      attribute,
    ]
  }
}

