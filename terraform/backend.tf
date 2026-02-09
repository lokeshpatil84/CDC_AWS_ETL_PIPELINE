# Terraform Backend Configuration
# This config tells Terraform to store state in S3 and use DynamoDB for locking

terraform {
  backend "s3" {
    bucket         = "cdc-pipeline-tfstate-dev"
    key            = "cdc-pipeline/terraform.tfstate"
    region         = "ap-south-1"
    dynamodb_table = "cdc-pipeline-terraform-lock-dev"
    encrypt        = true
  }
}

