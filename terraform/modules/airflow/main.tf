resource "aws_ecs_cluster" "airflow" {
  name = "${var.project_name}-${var.environment}-airflow"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-airflow"
  })
}

resource "aws_iam_role" "ecs_task_execution" {
  name = "${var.project_name}-${var.environment}-airflow-execution-role"

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

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-airflow-execution-role"
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "ecs_task" {
  name = "${var.project_name}-${var.environment}-airflow-task-role"

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

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-airflow-task-role"
  })
}

resource "aws_ecs_task_definition" "airflow" {
  family                   = "${var.project_name}-${var.environment}-airflow"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 512
  memory                   = 2048
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name    = "airflow-webserver"
      image   = "apache/airflow:2.7.0"
      command = ["webserver"]
      portMappings = [
        {
          containerPort = 8080
          hostPort      = 8080
        }
      ]
      environment = [
        { name = "AIRFLOW__CORE__EXECUTOR", value = "CeleryExecutor" },
        { name = "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN", value = var.airflow_db_conn },
        { name = "AIRFLOW__CELERY__BROKER_URL", value = var.celery_broker_url },
        { name = "AIRFLOW__CELERY__RESULT_BACKEND", value = var.celery_result_backend }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/aws/ecs/airflow"
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "airflow"
        }
      }
    },
    {
      name    = "airflow-scheduler"
      image   = "apache/airflow:2.7.0"
      command = ["scheduler"]
      environment = [
        { name = "AIRFLOW__CORE__EXECUTOR", value = "CeleryExecutor" },
        { name = "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN", value = var.airflow_db_conn },
        { name = "AIRFLOW__CELERY__BROKER_URL", value = var.celery_broker_url }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/aws/ecs/airflow"
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "scheduler"
        }
      }
    },
    {
      name    = "airflow-worker"
      image   = "apache/airflow:2.7.0"
      command = ["celery", "worker"]
      environment = [
        { name = "AIRFLOW__CORE__EXECUTOR", value = "CeleryExecutor" },
        { name = "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN", value = var.airflow_db_conn },
        { name = "AIRFLOW__CELERY__BROKER_URL", value = var.celery_broker_url }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/aws/ecs/airflow"
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "worker"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "airflow" {
  name            = "${var.project_name}-${var.environment}-airflow"
  cluster         = aws_ecs_cluster.airflow.id
  task_definition = aws_ecs_task_definition.airflow.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = var.private_subnet_ids
    security_groups = [aws_security_group.airflow.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.airflow.arn
    container_name   = "airflow-webserver"
    container_port   = 8080
  }
}

resource "aws_lb" "airflow" {
  name               = "${var.project_name}-${var.environment}-airflow"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.airflow.id]
  subnets            = var.public_subnet_ids
}

resource "aws_lb_target_group" "airflow" {
  name        = "${var.project_name}-${var.environment}-airflow"
  port        = 8080
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path = "/health"
  }
}

resource "aws_lb_listener" "airflow" {
  load_balancer_arn = aws_lb.airflow.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.airflow.arn
  }
}

resource "aws_security_group" "airflow" {
  name        = "${var.project_name}-${var.environment}-airflow-sg"
  description = "Security group for Airflow"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_cloudwatch_log_group" "airflow" {
  name              = "/aws/ecs/airflow"
  retention_in_days = 30
}


