resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-${var.environment}-ecs"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-ecs"
  })
}

resource "aws_iam_role" "ecs_task_execution" {
  name = "${var.project_name}-${var.environment}-ecs-task-exec"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_exec" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "ecs_secrets" {
  name = "${var.project_name}-${var.environment}-ecs-secrets"
  role = aws_iam_role.ecs_task_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action   = ["secretsmanager:GetSecretValue"]
        Effect   = "Allow"
        Resource = var.db_secret_arn
      },
      {
        Action   = ["kms:Decrypt"]
        Effect   = "Allow"
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role" "ecs_task" {
  name = "${var.project_name}-${var.environment}-ecs-task"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_ecs_task_definition" "debezium" {
  family                   = "${var.project_name}-${var.environment}-debezium"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name  = "debezium-connect"
      image = "debezium/connect:2.4"

      portMappings = [{ containerPort = 8083, hostPort = 8083, protocol = "tcp" }]

      environment = [
        { name = "BOOTSTRAP_SERVERS", value = var.kafka_bootstrap_servers },
        { name = "GROUP_ID", value = "debezium-cluster" },
        { name = "CONFIG_STORAGE_TOPIC", value = "debezium-configs" },
        { name = "OFFSET_STORAGE_TOPIC", value = "debezium-offsets" },
        { name = "STATUS_STORAGE_TOPIC", value = "debezium-status" },
        { name = "CONNECT_CONFIG_STORAGE_REPLICATION_FACTOR", value = "1" },
        { name = "CONNECT_OFFSET_STORAGE_REPLICATION_FACTOR", value = "1" },
        { name = "CONNECT_STATUS_STORAGE_REPLICATION_FACTOR", value = "1" },
        { name = "CONNECT_KEY_CONVERTER", value = "org.apache.kafka.connect.json.JsonConverter" },
        { name = "CONNECT_VALUE_CONVERTER", value = "org.apache.kafka.connect.json.JsonConverter" }
      ]

      secrets = [{ name = "DATABASE_PASSWORD", valueFrom = var.db_secret_arn }]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/aws/ecs/${var.project_name}-${var.environment}-debezium"
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "debezium"
        }
      }

      healthCheck = {
        command  = ["CMD-SHELL", "curl -f http://localhost:8083/connectors || exit 1"]
        interval = 30
        timeout  = 5
        retries  = 3
      }
    }
  ])
}

resource "aws_ecs_service" "debezium" {
  name            = "${var.project_name}-${var.environment}-debezium"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.debezium.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = [var.ecs_security_group_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.debezium.arn
    container_name   = "debezium-connect"
    container_port   = 8083
  }
}

resource "aws_lb" "debezium" {
  name               = "${var.project_name}-${var.environment}-debezium"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.ecs_security_group_id]
  subnets            = var.public_subnet_ids

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-debezium"
  })
}

resource "aws_lb_target_group" "debezium" {
  name        = "${var.project_name}-${var.environment}-debezium"
  port        = 8083
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = "/connectors"
    healthy_threshold   = 2
    unhealthy_threshold = 10
    timeout             = 30
    interval            = 60
  }
}

resource "aws_lb_listener" "debezium" {
  load_balancer_arn = aws_lb.debezium.arn
  port              = 8083
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.debezium.arn
  }
}

resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/aws/ecs/${var.project_name}-${var.environment}-debezium"
  retention_in_days = 30

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-ecs-logs"
  })
}


