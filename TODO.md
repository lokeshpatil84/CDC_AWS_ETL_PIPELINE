# CDC Pipeline End-to-End Execution Plan

## Current Status
- ✅ RDS PostgreSQL: Running (cdc-pipeline-dev-postgres.c3iy4ay6007a.ap-south-1.rds.amazonaws.com)
- ✅ VPC Endpoints: Secrets Manager, ECR API, ECR DKR deployed
- ✅ Security Groups: HTTPS egress rules added
- ✅ Secrets Manager: Access resolved
- ✅ ECS Task: RUNNING & HEALTHY (fixed - moved to public subnet with public IP)
- ⏳ Kafka: Needs verification
- ⏳ Debezium Connector: Needs setup
- ⏳ Glue Jobs: Not yet run

## Execution Steps

### Phase 1: Verify Infrastructure Status
- [x] Check ECS task status - RUNNING & HEALTHY
- [x] Verify Kafka EC2 instance is running
- [x] Check RDS connectivity
- [x] Verify VPC endpoints are working

### Phase 2: Fix Any Issues
- [x] Fix ECS task if still pending - FIXED (moved to public subnet with public IP)
- [x] Ensure Kafka is accessible
- [x] Verify security group rules

### Phase 3: Setup Debezium Connector
- [x] Get Debezium ALB URL - http://cdc-pipeline-dev-debezium-795892118.ap-south-1.elb.amazonaws.com:8083
- [ ] Run debezium_manager.py with AWS flag
- [ ] Verify connector is capturing changes

### Phase 4: Test Data Flow
- [ ] Insert test data into PostgreSQL
- [ ] Verify CDC events in Kafka
- [ ] Check S3 for Bronze data

### Phase 5: Run Glue Jobs
- [ ] Trigger Bronze to Silver job
- [ ] Trigger Silver to Gold job
- [ ] Verify data in all layers

### Phase 6: Validation
- [ ] Query Gold layer analytics
- [ ] Verify SCD Type 2 working
- [ ] Document results

