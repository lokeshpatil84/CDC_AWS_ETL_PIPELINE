# ECS Module Outputs
output "cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "service_name" {
  value = aws_ecs_service.debezium.name
}

output "task_definition_arn" {
  value = aws_ecs_task_definition.debezium.arn
}

output "task_execution_role_arn" {
  value = aws_iam_role.ecs_task_execution.arn
}

output "ecs_security_group_id" {
  description = "ECS Security Group ID from VPC module"
  value       = var.ecs_security_group_id
}

output "alb_dns_name" {
  value = aws_lb.debezium.dns_name
}

output "alb_zone_id" {
  value = aws_lb.debezium.zone_id
}

