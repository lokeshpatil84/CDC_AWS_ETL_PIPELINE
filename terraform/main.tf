terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}
data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  common_tags = var.tags
}

module "vpc" {
  source             = "./modules/vpc"
  project_name       = var.project_name
  environment        = var.environment
  vpc_cidr           = var.vpc_cidr
  availability_zones = slice(data.aws_availability_zones.available.names, 0, var.availability_zones)
  tags               = var.tags
}

resource "aws_key_pair" "kafka" {
  key_name   = var.key_name
  public_key = var.public_key

  lifecycle {
    create_before_destroy = true
  }
}

module "s3" {
  source                    = "./modules/s3"
  project_name              = var.project_name
  environment               = var.environment
  lifecycle_expiration_days = var.s3_lifecycle_expiration_days
  tags                      = var.tags
}

module "kafka" {
  source                = "./modules/kafka"
  project_name          = var.project_name
  environment           = var.environment
  vpc_id                = module.vpc.vpc_id
  vpc_cidr              = module.vpc.vpc_cidr
  subnet_id             = module.vpc.public_subnet_ids[0]
  ecs_security_group_id = module.vpc.ecs_security_group_id
  s3_bucket_name        = module.s3.data_bucket_name
  s3_bucket_arn         = module.s3.data_bucket_arn
  availability_zone     = slice(data.aws_availability_zones.available.names, 0, 1)[0]
  instance_type         = var.kafka_instance_type
  kafka_ami             = var.kafka_ami
  key_name              = var.key_name
  ebs_volume_size       = var.kafka_ebs_volume_size
  kafka_version         = var.kafka_version
  kafka_cluster_id      = var.kafka_cluster_id
  ssh_cidr_blocks       = var.ssh_cidr_blocks
  tags                  = var.tags
}

resource "aws_secretsmanager_secret" "db_credentials" {
  name                    = "${var.project_name}-${var.environment}-db-credentials"
  description             = "Database credentials for CDC pipeline"
  recovery_window_in_days = 0
  tags                    = var.tags

  lifecycle {
    ignore_changes        = [name]
    create_before_destroy = true
  }
}

resource "aws_secretsmanager_secret_version" "db_credentials" {
  secret_id = aws_secretsmanager_secret.db_credentials.id
  secret_string = jsonencode({
    username = var.db_username
    password = var.db_password
    host     = aws_db_instance.postgres.address
    port     = var.db_port
    database = var.db_name
  })
}

resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-${var.environment}-db-subnet"
  subnet_ids = module.vpc.private_subnet_ids
  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_db_instance" "postgres" {
  identifier        = "${var.project_name}-${var.environment}-postgres"
  engine            = "postgres"
  engine_version    = "15.10"
  instance_class    = var.db_instance_class
  allocated_storage = 20
  storage_encrypted = true

  db_name  = var.db_name
  username = var.db_username
  password = var.db_password
  port     = var.db_port

  vpc_security_group_ids = [module.vpc.postgres_security_group_id]
  db_subnet_group_name   = aws_db_subnet_group.main.name

  backup_retention_period = 0
  skip_final_snapshot     = true
  deletion_protection     = false

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-postgres"
  })
}

module "ecs" {
  source                  = "./modules/ecs"
  project_name            = var.project_name
  environment             = var.environment
  vpc_id                  = module.vpc.vpc_id
  subnet_ids              = module.vpc.private_subnet_ids
  public_subnet_ids       = module.vpc.public_subnet_ids
  cpu                     = var.ecs_cpu
  memory                  = var.ecs_memory
  db_secret_arn           = aws_secretsmanager_secret.db_credentials.arn
  kafka_bootstrap_servers = module.kafka.bootstrap_servers_internal
  aws_region              = var.aws_region
  tags                    = var.tags
  ecs_security_group_id   = module.vpc.ecs_security_group_id
}

module "glue" {
  source                  = "./modules/glue"
  project_name            = var.project_name
  environment             = var.environment
  s3_bucket_name          = module.s3.data_bucket_name
  worker_type             = var.glue_worker_type
  number_of_workers       = var.glue_number_of_workers
  glue_job_timeout        = var.glue_job_timeout
  aws_region              = var.aws_region
  kafka_bootstrap_servers = module.kafka.bootstrap_servers_internal
  tags                    = var.tags
}

module "airflow" {
  source             = "./modules/airflow"
  project_name       = var.project_name
  environment        = var.environment
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  public_subnet_ids  = module.vpc.public_subnet_ids
  s3_bucket_name     = module.s3.data_bucket_name
  aws_region         = var.aws_region
  tags               = var.tags
}

resource "aws_sns_topic" "alerts" {
  name = "${var.project_name}-${var.environment}-alerts"
  tags = var.tags
}

resource "aws_sns_topic_subscription" "email_alerts" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_cloudwatch_metric_alarm" "cost_alarm" {
  alarm_name          = "${var.project_name}-${var.environment}-cost-alarm"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "EstimatedCharges"
  namespace           = "AWS/Billing"
  period              = "86400"
  statistic           = "Maximum"
  threshold           = var.cost_threshold
  alarm_description   = "AWS estimated charges monitoring"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

