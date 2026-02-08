# Airflow Module Outputs
output "cluster_name" {
  value = aws_ecs_cluster.airflow.name
}

output "service_name" {
  value = aws_ecs_service.airflow.name
}

output "alb_dns_name" {
  value = aws_lb.airflow.dns_name
}

output "alb_zone_id" {
  value = aws_lb.airflow.zone_id
}

