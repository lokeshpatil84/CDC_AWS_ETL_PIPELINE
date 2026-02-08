# Terraform Bootstrap Outputs
# These outputs are used by the main Terraform configuration

output "s3_bucket_name" {
  description = "S3 bucket name for Terraform state"
  value       = aws_s3_bucket.terraform_state.bucket
}

output "s3_bucket_arn" {
  description = "S3 bucket ARN for Terraform state"
  value       = aws_s3_bucket.terraform_state.arn
}

output "dynamodb_table_name" {
  description = "DynamoDB table name for Terraform state locking"
  # Handle both existing table (via data source) and newly created table
  value = try(
    data.aws_dynamodb_table.existing_lock[0].name,
    aws_dynamodb_table.terraform_lock[0].name,
    var.dynamodb_table_name  # Fallback to variable
  )
}

output "dynamodb_table_arn" {
  description = "DynamoDB table ARN for Terraform state locking"
  # Handle both existing table (via data source) and newly created table
  value = try(
    data.aws_dynamodb_table.existing_lock[0].arn,
    aws_dynamodb_table.terraform_lock[0].arn,
    null  # ARN not available for existing table without read access
  )
}

output "bootstrap_complete" {
  description = "Bootstrap infrastructure is ready"
  value       = true
}

output "table_status" {
  description = "Status of DynamoDB table: 'existing', 'created', or 'pending'"
  value = try(
    data.aws_dynamodb_table.existing_lock[0].name != "" ? "existing" : "created",
    "created"
  )
}

