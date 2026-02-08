# ============================================================
# Terraform Variables
# ============================================================
# This file contains all variable definitions for the infrastructure.
# Override values using terraform.tfvars files or -var flags.
# ============================================================

variable "project_name" {
  type    = string
  default = "cdc-pipeline"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "availability_zones" {
  type    = number
  default = 2
}

variable "db_username" {
  type    = string
  default = "postgres"
}

variable "db_password" {
  type      = string
  default   = "postgres123!"
  sensitive = true
}

variable "db_instance_class" {
  type    = string
  default = "db.t3.micro"
}

variable "db_name" {
  type    = string
  default = "cdc_demo"
}

variable "db_port" {
  type    = number
  default = 5432
}

variable "ecs_cpu" {
  type    = number
  default = 256
}

variable "ecs_memory" {
  type    = number
  default = 512
}

variable "kafka_instance_type" {
  type    = string
  default = "t3.small"
}

variable "kafka_ami" {
  type    = string
  default = "ami-0ff5003538b60d5ec"
}

variable "key_name" {
  type    = string
  default = "kafka-key"
}

variable "public_key" {
  type        = string
  description = "SSH public key for Kafka EC2 instance access"
  default     = "" # User must provide this
}

variable "kafka_ebs_volume_size" {
  type    = number
  default = 30
}

variable "kafka_version" {
  type    = string
  default = "3.5.1"
}

variable "kafka_cluster_id" {
  type    = string
  default = "MkU3OEVBNTcwNTJENDM2Qk"
}

variable "glue_worker_type" {
  type    = string
  default = "G.1X"
}

variable "glue_number_of_workers" {
  type    = number
  default = 2
}

variable "glue_job_timeout" {
  type    = number
  default = 60
}

variable "cost_threshold" {
  type    = number
  default = 50
}

variable "alert_email" {
  type    = string
  default = "lokeshpatil8484@gmail.com"
}

variable "tags" {
  type = map(string)
  default = {
    Project     = "cdc-pipeline"
    Environment = "dev"
    ManagedBy   = "terraform"
    Owner       = "data-engineering-team"
  }
}

variable "s3_lifecycle_expiration_days" {
  type    = number
  default = 365
}

variable "ssh_cidr_blocks" {
  type        = string
  default     = "0.0.0.0/0"
  description = "CIDR blocks for SSH access to Kafka (restrict in production)"
}

