# ECS Module Variables
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

variable "subnet_ids" {
  type        = list(string)
  description = "Private subnet IDs"
}

variable "public_subnet_ids" {
  type        = list(string)
  description = "Public subnet IDs"
}

variable "cpu" {
  type        = number
  default     = 256
  description = "Task CPU units"
}

variable "memory" {
  type        = number
  default     = 512
  description = "Task memory in MiB"
}

variable "db_secret_arn" {
  type        = string
  description = "Secrets Manager ARN for DB credentials"
}

variable "kafka_bootstrap_servers" {
  type        = string
  description = "MSK bootstrap servers"
  default     = ""
  sensitive   = true
}

variable "aws_region" {
  type        = string
  description = "AWS region"
  default     = "ap-south-1"
}

variable "tags" {
  type = map(string)
  default = {
    Project     = "cdc-pipeline"
    Environment = "dev"
  }
}

variable "ecs_security_group_id" {
  type        = string
  description = "ECS Security Group ID from VPC module"
}

