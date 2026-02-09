# 🚀 AWS Real-Time CDC Data Pipeline

![Build Status](https://img.shields.io/github/actions/workflow/status/lokeshp6/cdc-pipeline/01_CI-check.yml?label=CI&logo=github)
![Terraform](https://img.shields.io/badge/Terraform-1.10.0-purple?logo=terraform)
![Python](https://img.shields.io/badge/Python-3.10-blue?logo=python)
![AWS](https://img.shields.io/badge/Cloud-AWS-orange?logo=amazon-aws)
![License](https://img.shields.io/badge/License-MIT-green)

A production-grade **Change Data Capture (CDC)** pipeline built on AWS. This project demonstrates an end-to-end data engineering solution that captures real-time database changes from PostgreSQL, streams them via Kafka, and processes them into a **Medallion Architecture** (Bronze/Silver/Gold) Data Lake using AWS Glue and **Apache Iceberg**.

---

## 🏗️ Architecture

The pipeline follows a modern event-driven architecture designed for scalability, fault tolerance, and data consistency.

```mermaid
%% If mermaid is supported, otherwise use ASCII below
graph LR
    DB[(PostgreSQL)] -->|WAL| Debezium[Debezium CDC]
    Debezium -->|JSON| Kafka[Apache Kafka]
    Kafka -->|Stream| Bronze[S3 Bronze\n(Raw JSON)]
    Bronze -->|Spark/Iceberg| Silver[S3 Silver\n(Cleaned/SCD2)]
    Silver -->|Spark/Iceberg| Gold[S3 Gold\n(Aggregated)]
    Airflow[Apache Airflow] -->|Orchestrate| Debezium
    Airflow -->|Trigger| Glue[AWS Glue Jobs]
```

### High-Level Data Flow

1.  **Ingestion Layer**:
    *   **Source**: Amazon RDS PostgreSQL (OLTP).
    *   **CDC Engine**: Debezium running on Amazon ECS (Fargate), reading the Write-Ahead Log (WAL).
    *   **Streaming**: Apache Kafka on EC2 acts as the message buffer.

2.  **Processing Layer (AWS Glue)**:
    *   **Bronze (Raw)**: Ingests raw CDC events from Kafka to S3.
    *   **Silver (Refined)**: Applies schema enforcement and **SCD Type 2** (Slowly Changing Dimensions) logic using **Apache Iceberg**.
    *   **Gold (Business)**: Aggregates data for analytics (e.g., User RFM analysis, Sales summaries).

3.  **Orchestration & Control**:
    *   **Apache Airflow**: Manages workflow dependencies, health checks, and job triggers.
    *   **Terraform**: Fully manages infrastructure as code (IaC).

---

## 🌟 Key Features

*   **Real-Time Capture**: Millisecond-latency change capture using Debezium.
*   **ACID Transactions**: Uses **Apache Iceberg** for reliable data lake updates and time-travel queries.
*   **SCD Type 2**: Historically accurate data tracking (handling updates/deletes) in the Silver layer.
*   **Infrastructure as Code**: Modular Terraform setup for VPC, ECS, RDS, and Glue.
*   **CI/CD**: GitHub Actions pipelines for code quality (flake8, black, tflint) and automated deployment.
*   **Observability**: Integrated CloudWatch logging, metrics, and SNS alerts for failures/costs.
*   **Security**: VPC isolation, private subnets, Security Groups, and Secrets Manager integration.

---

## 🛠️ Tech Stack

| Category | Technology | Description |
| :--- | :--- | :--- |
| **Cloud Provider** | AWS | Region: `ap-south-1` (Mumbai) |
| **IaC** | Terraform | Infrastructure provisioning & state management |
| **Database** | RDS PostgreSQL | Source transactional database |
| **Streaming** | Apache Kafka | Message broker (EC2 `t3.small`) |
| **CDC** | Debezium | Connect platform (ECS Fargate) |
| **ETL/Compute** | AWS Glue | Serverless Spark jobs (PySpark) |
| **Storage** | Amazon S3 | Data Lake storage |
| **Table Format** | Apache Iceberg | Open table format for analytic datasets |
| **Orchestration** | Apache Airflow | Workflow management (ECS Fargate) |
| **CI/CD** | GitHub Actions | Automated testing and deployment |

---

## 📂 Project Structure

```bash
.
├── .github/workflows/      # CI/CD Pipelines (Quality Check & Deployment)
├── airflow/                # Airflow DAGs and configurations
├── debezium/               # Debezium connector scripts & manager
├── glue/                   # PySpark ETL Jobs
│   ├── kafka_to_bronze.py  # Stream ingestion
│   ├── bronze_to_silver.py # SCD Type 2 logic
│   └── silver_to_gold.py   # Business aggregations
├── sql/                    # Database initialization scripts
├── terraform/              # Main Infrastructure code
└── terraform-bootstrap/    # State bucket & Lock table setup
```

---

## 🚀 Getting Started

### Prerequisites

*   AWS CLI configured with Administrator access.
*   Terraform (v1.10+).
*   Python (v3.10+).
*   SSH Key Pair (for Kafka EC2 access).

### 1. Infrastructure Deployment

**Step 1: Bootstrap Backend**
Initialize the S3 bucket for Terraform state and DynamoDB for locking.

```bash
cd terraform-bootstrap
terraform init
terraform apply -var-file=terraform.tfvars.dev
```

**Step 2: Deploy Main Stack**
Deploy the VPC, RDS, ECS, Kafka, and Glue resources.

```bash
cd ../terraform
terraform init -backend-config="bucket=cdc-pipeline-tfstate-dev"
terraform apply -var-file=terraform.tfvars.dev
```

### 2. Configure Debezium Connector

Once infrastructure is up, configure the Debezium connector to start capturing changes.

```bash
# Export endpoints from Terraform output
export DEBEZIUM_URL=$(terraform output -raw debezium_connect_url)

# Run the manager script
cd ../debezium
python3 debezium_manager.py --aws --create
```

### 3. Verify Pipeline

1.  **Access Airflow**: `http://<airflow-alb-url>`
2.  **Check Kafka Topics**:
    ```bash
    ssh -i key.pem ec2-user@<kafka-ip> "kafka-topics.sh --list --bootstrap-server localhost:9092"
    ```
3.  **Generate Data**: Connect to RDS and insert/update records.
4.  **Run Glue Jobs**: Trigger via Airflow or AWS Console.

---

## 📊 Data Models

### Silver Layer (Iceberg)
The Silver layer implements **SCD Type 2** to track history.

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | Long | Primary Key |
| `...` | ... | Business columns |
| `_valid_from` | Timestamp | Start of record validity |
| `_valid_to` | Timestamp | End of record validity (NULL if current) |
| `_is_current` | Boolean | Flag for quick current-state queries |
| `operation` | String | `c` (create), `u` (update), `d` (delete) |

### Gold Layer (Aggregates)
Example: **User Analytics** (`gold_user_analytics`)
*   `user_id`
*   `total_spent`
*   `recency_days`
*   `segment` (VIP, Loyal, New)

---

## 🛡️ Security & Network

*   **VPC Design**:
    *   **Public Subnets**: ALBs, NAT Gateway, Bastion Host.
    *   **Private Subnets**: RDS, ECS Tasks, Glue ENIs, Kafka Broker.
*   **Access Control**:
    *   Kafka is accessible only via SSH Tunnel or internal VPC traffic.
    *   RDS allows access only from ECS/Glue security groups.
*   **Secrets**: Database credentials managed in **AWS Secrets Manager**.

---

## 💰 Cost Estimation (Dev)

Approximate monthly cost for the development environment in `ap-south-1`:

| Service | Configuration | Est. Cost |
| :--- | :--- | :--- |
| **RDS** | db.t3.micro | ~$15.00 |
| **EC2 (Kafka)** | t3.small | ~$15.00 |
| **NAT Gateway** | Managed | ~$30.00 |
| **Glue/ECS** | On-demand | ~$15.00 |
| **Total** | | **~$75.00 / mo** |

*Note: Production environments should use Multi-AZ RDS and larger instances.*

---

## 🤝 Contributing

1.  Fork the repository.
2.  Create a feature branch (`git checkout -b feature/amazing-feature`).
3.  Commit changes (`git commit -m 'Add amazing feature'`).
4.  Push to branch (`git push origin feature/amazing-feature`).
5.  Open a Pull Request.

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.

---

**Maintained by [Lokesh Patil]**
