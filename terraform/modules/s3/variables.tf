# S3 Module Variables
variable "project_name" {
  type        = string
  description = "Project name for resource naming"
}

variable "environment" {
  type        = string
  description = "Environment name"
}

variable "lifecycle_expiration_days" {
  type        = number
  description = "Days before objects are deleted"
  default     = 365
}

variable "tags" {
  type        = map(string)
  description = "Common tags"
  default = {
    Project     = "cdc-pipeline"
    Environment = "dev"
    ManagedBy   = "terraform"
  }
}

