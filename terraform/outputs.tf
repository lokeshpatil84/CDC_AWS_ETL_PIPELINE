# ============================================================
# Terraform Outputs
# ============================================================
# This file contains all output values for the infrastructure.
# Run 'terraform output' to view these values after apply.
# ============================================================

output "project_name" {
  value = var.project_name
}

output "environment" {
  value = var.environment
}

output "vpc_id" {
  value = module.vpc.vpc_id
}

output "public_subnet_ids" {
  value = module.vpc.public_subnet_ids
}

output "private_subnet_ids" {
  value = module.vpc.private_subnet_ids
}

output "s3_data_lake_bucket" {
  value = module.s3.data_bucket_name
}

output "kafka_public_ip" {
  value       = module.kafka.kafka_public_ip
  description = "Public IP of Kafka EC2 instance"
}

output "kafka_bootstrap_servers" {
  value     = module.kafka.bootstrap_servers
  sensitive = true
}

output "kafka_bootstrap_servers_internal" {
  value     = module.kafka.bootstrap_servers_internal
  sensitive = true
}

output "kafka_security_group_id" {
  value = module.kafka.security_group_id
}

output "rds_endpoint" {
  value = aws_db_instance.postgres.endpoint
}

output "database_endpoint" {
  value       = aws_db_instance.postgres.endpoint
  description = "Database endpoint (alias for rds_endpoint)"
}

output "debezium_connect_url" {
  value = "http://${module.ecs.alb_dns_name}:8083"
}

output "airflow_url" {
  value = "http://${module.airflow.alb_dns_name}"
}

output "service_url" {
  value       = "Airflow: http://${module.airflow.alb_dns_name}\nDebezium: http://${module.ecs.alb_dns_name}:8083"
  description = "Combined service URLs for deployed infrastructure"
}

output "glue_role_arn" {
  value = module.glue.role_arn
}

output "db_secret_arn" {
  value = aws_secretsmanager_secret.db_credentials.arn
}

output "sns_topic_arn" {
  value = aws_sns_topic.alerts.arn
}

