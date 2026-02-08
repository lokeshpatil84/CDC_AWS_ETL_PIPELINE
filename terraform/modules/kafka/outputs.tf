output "kafka_instance_id" {
  value       = aws_instance.kafka.id
  description = "EC2 instance ID for Kafka"
}

output "kafka_public_ip" {
  value       = aws_eip.kafka.public_ip
  description = "Public IP of Kafka instance"
}

output "kafka_dns_name" {
  value       = aws_instance.kafka.public_dns
  description = "DNS name of Kafka instance"
}

output "bootstrap_servers" {
  value       = "${aws_eip.kafka.public_ip}:9092"
  sensitive   = true
  description = "Kafka bootstrap servers (PLAINTEXT)"
}

output "bootstrap_servers_internal" {
  value       = "${aws_instance.kafka.private_ip}:9092"
  sensitive   = true
  description = "Kafka bootstrap servers for internal/ECS access"
}

output "security_group_id" {
  value       = aws_security_group.kafka.id
  description = "Security group ID for Kafka"
}

output "kafka_version" {
  value       = var.kafka_version
  description = "Apache Kafka version"
}

