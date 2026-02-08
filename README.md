# CDC Pipeline - AWS Data Engineering Project

A production-grade Change Data Capture (CDC) pipeline built on AWS that captures real-time database changes using Debezium, processes them through Apache Kafka, and transforms data using AWS Glue before storing in a data lake architecture (Bronze → Silver → Gold).

## 📋 Table of Contents

- [Architecture Overview](#-architecture-overview)
- [Features](#-features)
- [Prerequisites](#-prerequisites)
- [Quick Start](#-quick-start)
- [Project Structure](#-project-structure)
- [Infrastructure Components](#-infrastructure-components)
- [Deployment Guide](#-deployment-guide)
- [Configuration](#-configuration)
- [Data Pipeline Flow](#-data-pipeline-flow)
- [Monitoring & Observability](#-monitoring--observability)
- [Security Best Practices](#-security-best-practices)
- [Cost Optimization](#-cost-optimization)
- [Troubleshooting](#-troubleshooting)
- [Cleanup](#-cleanup)

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              CDC Pipeline Architecture                           │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Source DB  │───▶│  Debezium   │───▶│   Apache    │───▶│   Bronze    │
│  (PostgreSQL)│    │  (ECS/Fargate)│    │   Kafka    │    │   (S3)      │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
                                                  │              │
                                                  │              ▼
                                           ┌──────┴──────┐    ┌─────────────┐
                                           │   AWS Glue   │───▶│   Silver    │
                                           │   Jobs       │    │   (S3/Iceberg)│
                                           └──────────────┘    └─────────────┘
                                                                   │
                                                                   ▼
                                                          ┌─────────────┐
                                                          │    Gold     │
                                                          │  (Aggregated)│
                                                          └─────────────┘
                                                                   │
                                                                   ▼
                                                          ┌─────────────┐
                                                          │  Airflow    │
                                                          │  Orchestration│
                                                          └─────────────┘
```

### Key Components

| Component | Purpose | AWS Service |
|-----------|---------|-------------|
| **Source Database** | Captures real-time changes | PostgreSQL (RDS) |
| **CDC Connector** | Streams DB changes to Kafka | Debezium (ECS Fargate) |
| **Message Broker** | Buffer and transport events | Apache Kafka (EC2) |
| **Bronze Layer** | Raw change data capture | S3 Bucket |
| **Silver Layer** | Cleaned and enriched data | S3 + Iceberg |
| **Gold Layer** | Business-level aggregations | S3 + Iceberg |
| **Orchestration** | Workflow management | Apache Airflow (ECS Fargate) |
| **Infrastructure** | Cloud resources | Terraform |

---

## ✨ Features

- 🚀 **Real-time CDC**: Capture database changes instantly using Debezium
- 📊 **Medallion Architecture**: Bronze → Silver → Gold data transformation
- 🧊 **Iceberg Integration**: ACID transactions, time travel, schema evolution
- 🔄 **Exactly-Once Processing**: Reliable data processing semantics
- 📈 **Scalable**: Auto-scaling Glue jobs, managed Kafka
- 🔒 **Secure**: VPC isolation, encryption at rest/transit, IAM roles
- 📝 **Observable**: CloudWatch metrics, logs, and alerts
- 🛠️ **Production-Ready**: Terraform IaC, structured logging, monitoring

---

## 📋 Prerequisites

### Required Tools

| Tool | Version | Purpose |
|------|---------|---------|
| AWS CLI | ≥ 2.0 | AWS resource management |
| Terraform | ≥ 1.0 | Infrastructure as Code |
| Python | ≥ 3.9 | Glue job scripts |
| Docker | Latest | Container builds |

### AWS Account Setup

1. **IAM User/Role** with permissions:
   - `AdministratorAccess` (for initial setup)
   - Or specific permissions for: EC2, RDS, S3, IAM, Glue, ECS, VPC, CloudWatch

2. **AWS CLI Configuration**:
   ```bash
   aws configure
   aws configure set region ap-south-1
   ```

3. **S3 Backend Bucket** (created by terraform-bootstrap):
   ```bash
   # Bucket: cdc-pipeline-tfstate-{environment}
   # DynamoDB Table: cdc-pipeline-terraform-lock-{environment}
   ```

---

## 🚀 Quick Start

### 1. Clone and Setup

```bash
git clone <repository-url>
cd local_aws_etl_pipline
```

### 2. Configure Environment

```bash
# Copy environment template
cp terraform/terraform.tfvars.dev terraform/terraform.tfvars

# Edit with your values
vim terraform/terraform.tfvars
```

Required variables:
```hcl
environment   = "dev"          # dev, staging, prod
aws_region    = "ap-south-1"   # Your AWS region
public_key    = "ssh-ed25519..."  # SSH key for Kafka access
alert_email   = "your@email.com"  # Cost alert notifications
```

### 3. Deploy Infrastructure

```bash
# Step 1: Deploy backend infrastructure (S3 + DynamoDB)
cd terraform-bootstrap
terraform init
terraform apply -var-file=terraform.tfvars.dev

# Step 2: Deploy main infrastructure
cd ../terraform
terraform init -reconfigure -backend-config="bucket=cdc-pipeline-tfstate-dev"
terraform apply -var-file=terraform.tfvars.dev
```

### 4. Verify Deployment

```bash
# Check outputs
terraform output

# Verify resources in AWS Console
aws s3 ls | grep cdc-pipeline
aws ec2 describe-instances --filters "Name=tag:Project,Values=cdc-pipeline"
```

---

## 📁 Project Structure

```
local_aws_etl_pipline/
├── README.md                    # This file
├── docker-compose.yml          # Local development
├── requirements.txt            # Python dependencies
│
├── airflow/                    # Airflow DAGs
│   └── dags/
│       └── cdc_pipeline_dag.py # Main pipeline orchestration
│
├── debezium/                   # Debezium connector configs
│   └── debezium_manager.py    # Connector management
│
├── glue/                       # AWS Glue job scripts
│   ├── kafka_to_bronze.py      # Raw CDC data to Bronze
│   ├── bronze_to_silver.py     # Bronze to Silver (SCD Type 2)
│   └── silver_to_gold.py       # Silver to Gold aggregations
│
├── sql/                        # Database initialization
│   ├── init.sql               # Schema setup
│   └── seed_data.sql          # Sample data
│
└── terraform/                  # Infrastructure as Code
    ├── backend.tf             # S3 backend configuration
    ├── main.tf                # Main infrastructure
    ├── variables.tf           # Variable definitions
    ├── outputs.tf             # Output definitions
    ├── terraform.tfvars.dev   # Dev environment config
    └── terraform.tfvars.prod  # Production config
    │
    └── modules/               # Terraform modules
        ├── airflow/           # Airflow on ECS
        ├── ecs/              # ECS (Debezium)
        ├── glue/             # Glue jobs
        ├── kafka/            # Kafka on EC2
        ├── s3/               # S3 buckets
        └── vpc/              # Network setup
```

---

## 🏗️ Infrastructure Components

### VPC & Networking

| Resource | Description |
|----------|-------------|
| **VPC** | 10.0.0.0/16 network |
| **Public Subnets** | 2 AZs for ALBs and bastion access |
| **Private Subnets** | 2 AZs for services |
| **Internet Gateway** | Egress for public subnets |
| **NAT Gateway** | Egress for private subnets |

### Compute

| Resource | Type | Purpose |
|----------|------|---------|
| **Kafka** | EC2 (t3.small) | Message broker |
| **Debezium** | ECS Fargate | CDC connector |
| **Airflow** | ECS Fargate | Orchestration |

### Data

| Resource | Tier | Purpose |
|----------|------|---------|
| **PostgreSQL** | db.t3.micro | Source database |
| **S3 Buckets** | 4 buckets | Data lake storage |

---

## 📖 Deployment Guide

### Environment Setup

#### Development
```bash
# Configure dev environment
export TF_VAR_environment=dev
export TF_VAR_aws_region=ap-south-1
```

#### Staging
```bash
# Configure staging environment
export TF_VAR_environment=staging
export TF_VAR_aws_region=ap-south-1
```

#### Production
```bash
# Production requires:
# 1. Separate AWS account or strict isolation
# 2. Multi-AZ deployment (already configured)
# 3. Enhanced monitoring enabled
# 4. Backup and disaster recovery configured

export TF_VAR_environment=prod
export TF_VAR_cost_threshold=100  # Lower threshold for alerts
```

### Terraform Commands

```bash
# Initialize backend
terraform init -reconfigure \
  -backend-config="bucket=cdc-pipeline-tfstate-dev" \
  -backend-config="region=ap-south-1"

# Plan changes
terraform plan -var-file=terraform.tfvars.dev

# Apply changes
terraform apply -var-file=terraform.tfvars.dev

# Destroy (WARNING: Removes all resources)
terraform destroy -var-file=terraform.tfvars.dev
```

---

## ⚙️ Configuration

### Terraform Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `environment` | `dev` | Environment name |
| `aws_region` | `ap-south-1` | AWS region |
| `project_name` | `cdc-pipeline` | Project prefix |
| `vpc_cidr` | `10.0.0.0/16` | VPC CIDR block |
| `db_instance_class` | `db.t3.micro` | RDS instance type |
| `kafka_instance_type` | `t3.small` | Kafka EC2 type |
| `glue_worker_type` | `G.1X` | Glue job workers |
| `ecs_cpu` | `256` | ECS task CPU |
| `ecs_memory` | `512` | ECS task memory |

### Glue Job Configuration

Jobs are configured with:
- **Glue Version**: 4.0
- **Python Version**: 3
- **Workers**: 2 (configurable)
- **Timeout**: 60 minutes
- **Python Modules**: `pyiceberg==0.5.1`

### Kafka Configuration

| Setting | Value |
|---------|-------|
| Version | 3.5.1 |
| Port | 9092 |
| Security | SASL (when enabled) |
| Retention | 7 days |

---

## 🔄 Data Pipeline Flow

### 1. Bronze Layer (Raw CDC)

```
Source DB → Debezium → Kafka Topic → S3 Bronze Bucket
```

**Format**: JSON with CDC payload
```json
{
  "before": null,
  "after": {"id": 1, "name": "test", "updated_at": "2024-01-01"},
  "source": {"version": "2.4.0", "connector": "postgresql"},
  "op": "c",  // c=create, u=update, d=delete, r=read
  "ts_ms": 1704067200000
}
```

### 2. Silver Layer (Cleaned & Enriched)

```
Bronze → Glue Job → S3 Silver (Iceberg) → Delta Tracking
```

**Transformations**:
- Schema enforcement
- Data type normalization
- Deduplication (SCD Type 2)
- Enrichment joins

### 3. Gold Layer (Business Aggregates)

```
Silver → Glue Job → S3 Gold (Iceberg) → Analytics Ready
```

**Aggregations**:
- Daily summaries
- Window functions
- Business KPIs
- Materialized views

### Airflow DAG

The `cdc_pipeline_dag.py` orchestrates:
1. Check Kafka connectivity
2. Trigger Bronze → Silver job
3. Trigger Silver → Gold job
4. Validate outputs
5. Send notifications

---

## 📊 Monitoring & Observability

### CloudWatch Metrics

| Namespace | Metrics |
|-----------|---------|
| `AWS/Billing` | Estimated charges |
| `AWS/ECS` | Task count, CPU, memory |
| `AWS/Glue` | Job success/failure, execution time |
| `AWS/S3` | Bucket size, object count |

### CloudWatch Logs

| Service | Log Group |
|---------|-----------|
| Airflow | `/aws/ecs/airflow` |
| Debezium | `/aws/ecs/cdc-pipeline-dev-debezium` |
| Glue | `/aws/glue/cdc-pipeline-{env}` |

### Alerts Configured

| Alert | Threshold | Action |
|-------|-----------|--------|
| Cost Alert | $50/month | SNS email notification |
| Glue Job Failure | Any | SNS email |

### Viewing Logs

```bash
# Airflow logs
aws logs tail /aws/ecs/airflow --follow

# Glue job logs
aws logs tail /aws/glue/cdc-pipeline-dev --follow
```

---

## 🔒 Security Best Practices

### Network Security

- ✅ **VPC Isolation**: All services in private subnets
- ✅ **Security Groups**: Least-privilege access
- ✅ **No Public IPs**: Services not exposed directly

### Data Security

- ✅ **Encryption at Rest**: All S3 buckets, RDS, EBS encrypted
- ✅ **Encryption in Transit**: TLS enabled
- ✅ **IAM Roles**: No long-lived credentials

### Secrets Management

```bash
# Database credentials stored in Secrets Manager
aws secretsmanager get-secret-value \
  --secret-id cdc-pipeline-dev-db-credentials
```

### Recommended Additional Security

1. **Enable VPC Flow Logs** for network monitoring
2. **Configure AWS GuardDuty** for threat detection
3. **Enable AWS Config** for compliance
4. **Implement AWS CloudTrail** for audit logging
5. **Use AWS KMS** for encryption key management

---

## 💰 Cost Optimization

### Estimated Monthly Costs (ap-south-1)

| Service | Estimate |
|---------|----------|
| RDS (db.t3.micro) | ~$15 |
| Kafka (t3.small) | ~$15 |
| NAT Gateway | ~$30 |
| Glue Jobs | ~$10 (light usage) |
| S3 Storage | ~$5 |
| CloudWatch | ~$5 |
| **Total** | ~$80/month |

### Cost Saving Tips

1. **Use dev environment sparingly**: Destroy when not in use
2. **Right-size instances**: Start small, scale as needed
3. **Schedule Glue jobs**: Run during off-peak hours
4. **Lifecycle policies**: Automatically expire old data
5. **Use AWS Free Tier**: First 12 months include many free resources

---

## 🛠️ Troubleshooting

### Common Issues

#### 1. Terraform Backend Error

```bash
Error: Failed to get existing workspaces
# Cause: S3 bucket doesn't exist
# Fix: Run terraform-bootstrap first
cd terraform-bootstrap
terraform apply
```

#### 2. Kafka Connection Refused

```bash
# Check if Kafka is running
ssh -i kafka-key.pem ec2-user@<kafka-public-ip>
systemctl status kafka

# Check security group allows port 9092
aws ec2 describe-security-groups \
  --filters "Name=tag:Name,Values=*kafka*"
```

#### 3. Glue Job Failures

```bash
# Check CloudWatch logs
aws logs describe-log-groups \
  --log-group-name-prefix /aws/glue/cdc-pipeline

# Common issues:
# - Missing S3 bucket (check terraform outputs)
# - Script path incorrect
# - IAM role permissions
```

#### 4. Debezium Connector Not Starting

```bash
# Check ECS service
aws ecs describe-services \
  --cluster cdc-pipeline-dev-ecs \
  --service cdc-pipeline-dev-debezium

# Check task logs
aws logs tail /aws/ecs/cdc-pipeline-dev-debezium --follow
```

### Useful Commands

```bash
# List all resources
aws resourcegroupstaggingapi get-resources \
  --tag-filters Key=Project,Values=cdc-pipeline

# Check running costs
aws ce get-cost-and-usage \
  --time-period Start=2024-01-01,End=2024-01-31 \
  --granularity MONTHLY \
  --metrics "BlendedCost" \
  --group-by Type=DIMENSION,Key=SERVICE
```

---

## 🧹 Cleanup

### Destroy All Resources

```bash
# IMPORTANT: This will delete all data!
cd terraform
terraform destroy -var-file=terraform.tfvars.dev

# Optionally destroy backend (after main is destroyed)
cd ../terraform-bootstrap
terraform destroy -var-file=terraform.tfvars.dev
```

### Selective Cleanup

```bash
# Destroy only Glue jobs
terraform destroy -target=module.glue

# Destroy only Kafka
terraform destroy -target=module.kafka
```

---

## 📚 Additional Resources

### AWS Documentation

- [AWS Glue Developer Guide](https://docs.aws.amazon.com/glue/latest/dg/)
- [Amazon RDS PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_PostgreSQL.html)
- [Debezium Documentation](https://debezium.io/documentation/)
- [Apache Kafka on AWS](https://aws.amazon.com/msk/)

### Architecture Patterns

- [AWS Well-Architected Framework](https://aws.amazon.com/architecture/well-architected/)
- [Medallion Architecture](https://www.databricks.com/glossary/medallion-architecture)

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run `terraform plan` to verify
5. Submit a pull request

---

## 📄 License

This project is licensed under the MIT License.

---

## 🆘 Support

For issues and questions:

1. Check the [Troubleshooting](#troubleshooting) section
2. Review CloudWatch logs
3. Search existing GitHub issues
4. Create a new issue with:
   - Environment details
   - Error message
   - Steps to reproduce
   - Expected behavior

---

**Last Updated**: January 2025
**Version**: 1.0.0

