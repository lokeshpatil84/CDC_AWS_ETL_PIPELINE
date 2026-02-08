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

variable "subnet_id" {
  type        = string
  description = "Public subnet ID for Kafka EC2"
}

variable "ecs_security_group_id" {
  type        = string
  description = "ECS security group ID for allowing Kafka access"
}

variable "s3_bucket_name" {
  type        = string
  description = "S3 bucket name for scripts"
}

variable "s3_bucket_arn" {
  type        = string
  description = "S3 bucket ARN"
}

variable "availability_zone" {
  type        = string
  description = "Availability zone for EBS volume"
}

variable "instance_type" {
  type        = string
  default     = "t3.medium"
  description = "EC2 instance type for Kafka"
}

variable "kafka_ami" {
  type        = string
  default     = "ami-0e599a3e2c7539841"
  description = "AMI ID for Kafka EC2 instance"
}

variable "key_name" {
  type        = string
  default     = "kafka-key"
  description = "SSH key pair name"
}

variable "ebs_volume_size" {
  type        = number
  default     = 100
  description = "EBS volume size in GB for Kafka data"
}

variable "kafka_version" {
  type        = string
  default     = "3.5.1"
  description = "Apache Kafka version"
}

variable "kafka_cluster_id" {
  type        = string
  default     = "MkU3OEVBNTcwNTJENDM2Qk"
  description = "KRaft cluster ID"
}

variable "tags" {
  type = map(string)
  default = {
    Project     = "cdc-pipeline"
    Environment = "dev"
  }
}

variable "ssh_cidr_blocks" {
  type        = string
  description = "CIDR blocks for SSH access (restrict in production)"
}

variable "vpc_cidr" {
  type        = string
  description = "VPC CIDR block for internal access"
}

