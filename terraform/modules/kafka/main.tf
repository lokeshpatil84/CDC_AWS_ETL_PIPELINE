resource "aws_iam_role" "kafka_ec2_role" {
  name = "${var.project_name}-${var.environment}-kafka-ec2-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_instance_profile" "kafka_ec2_profile" {
  name = "${var.project_name}-${var.environment}-kafka-ec2-profile"
  role = aws_iam_role.kafka_ec2_role.name
}

resource "aws_iam_policy" "kafka_s3_policy" {
  name = "${var.project_name}-${var.environment}-kafka-s3-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject"
        ]
        Effect   = "Allow"
        Resource = "${var.s3_bucket_arn}/*"
      },
      {
        Action = [
          "s3:ListBucket"
        ]
        Effect   = "Allow"
        Resource = var.s3_bucket_arn
      },
      {
        Action = [
          "cloudwatch:PutMetricData"
        ]
        Effect   = "Allow"
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "kafka_s3_attach" {
  role       = aws_iam_role.kafka_ec2_role.name
  policy_arn = aws_iam_policy.kafka_s3_policy.arn
}

resource "aws_security_group" "kafka" {
  name        = "${var.project_name}-${var.environment}-kafka-sg"
  description = "Security group for Kafka on EC2"
  vpc_id      = var.vpc_id

  # SSH access - restricted to specific CIDR (change to your IP in tfvars)
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.ssh_cidr_blocks] # Default: 0.0.0.0/0 - RESTRICT IN PRODUCTION
  }

  # Kafka client port - VPC internal only
  ingress {
    from_port   = 9092
    to_port     = 9092
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr] # VPC internal only
  }

  # Controller port - VPC internal only
  ingress {
    from_port   = 9093
    to_port     = 9093
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr] # VPC internal only
  }

  # JMX monitoring - VPC internal only
  ingress {
    from_port   = 9100
    to_port     = 9100
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr] # VPC internal only
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = var.tags
}

resource "aws_security_group_rule" "kafka_from_ecs" {
  type                     = "ingress"
  from_port                = 9092
  to_port                  = 9092
  protocol                 = "tcp"
  source_security_group_id = var.ecs_security_group_id
  security_group_id        = aws_security_group.kafka.id
}

resource "aws_eip" "kafka" {
  domain = "vpc"

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-kafka-eip"
  })
}

resource "aws_ebs_volume" "kafka_data" {
  availability_zone = var.availability_zone
  size              = var.ebs_volume_size
  type              = "gp3"

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-kafka-data"
  })
}

resource "aws_instance" "kafka" {
  ami                         = var.kafka_ami
  instance_type               = var.instance_type
  key_name                    = var.key_name
  subnet_id                   = var.subnet_id
  vpc_security_group_ids      = [aws_security_group.kafka.id]
  iam_instance_profile        = aws_iam_instance_profile.kafka_ec2_profile.name
  associate_public_ip_address = true
  disable_api_termination     = false

  root_block_device {
    volume_size           = 20
    volume_type           = "gp3"
    delete_on_termination = true
  }

  user_data = templatefile("${path.module}/kafka_setup.tftpl", {
    kafka_version  = var.kafka_version
    cluster_id     = var.kafka_cluster_id
    log_dir        = "/var/log/kafka"
    ebs_device     = "/dev/sdb"
    s3_bucket_name = var.s3_bucket_name
  })

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-kafka"
  })
}

resource "aws_volume_attachment" "kafka_data" {
  device_name  = "/dev/sdb"
  volume_id    = aws_ebs_volume.kafka_data.id
  instance_id  = aws_instance.kafka.id
  force_detach = true
}

resource "aws_eip_association" "kafka" {
  instance_id   = aws_instance.kafka.id
  allocation_id = aws_eip.kafka.id
}

