# Glue Module Outputs
output "kafka_to_bronze_job_name" {
  value = aws_glue_job.kafka_to_bronze.name
}

output "bronze_to_silver_job_name" {
  value = aws_glue_job.bronze_to_silver.name
}

output "silver_to_gold_job_name" {
  value = aws_glue_job.silver_to_gold.name
}

output "role_arn" {
  value = aws_iam_role.glue_role.arn
}

output "role_name" {
  value = aws_iam_role.glue_role.name
}

output "database_name" {
  value = aws_glue_catalog_database.data_lake.name
}

