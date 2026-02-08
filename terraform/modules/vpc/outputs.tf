output "vpc_id" {
  value = aws_vpc.main.id
}

output "vpc_cidr" {
  value = aws_vpc.main.cidr_block
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}

output "availability_zones" {
  value = var.availability_zones
}

output "internet_gateway_id" {
  value = aws_internet_gateway.igw.id
}

output "nat_gateway_id" {
  value = aws_nat_gateway.nat.id
}

output "default_security_group_id" {
  value = aws_security_group.default.id
}

output "postgres_security_group_id" {
  value = aws_security_group.postgres.id
}

output "ecs_security_group_id" {
  value = aws_security_group.ecs.id
}

output "glue_security_group_id" {
  value = aws_security_group.glue.id
}

