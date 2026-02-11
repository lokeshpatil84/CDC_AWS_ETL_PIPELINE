variable "project_name" {
  type        = string
  description = "Project name for resource naming"
}

variable "environment" {
  type        = string
  description = "Environment name (dev, staging, prod)"
}

variable "vpc_cidr" {
  type        = string
  description = "CIDR block for the VPC"
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  type        = list(string)
  description = "List of availability zones to use"
}

variable "tags" {
  type        = map(string)
  description = "Common tags for all resources"
  default = {
    Project     = "cdc-pipeline"
    Environment = "dev"
    ManagedBy   = "terraform"
  }
}

variable "local_ip_cidr_blocks" {
  type        = list(string)
  description = "Local IP CIDR blocks to allow PostgreSQL access from (for debugging)"
  default     = []
}

variable "aws_region" {
  type        = string
  description = "AWS region for VPC endpoints"
  default     = "ap-south-1"
}
