---
phase: 07-aws-deployment
verified: 2026-04-20T00:00:00Z
status: human_needed
score: 13/15 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Run terraform apply in infra/environments/dev with AWS credentials and a valid ACM certificate ARN set in terraform.tfvars"
    expected: "All ECS services reach RUNNING/HEALTHY state; gateway, admin-api, echo, and ping tasks stabilize with desired_count=1"
    why_human: "Cannot provision real AWS infrastructure without credentials; terraform plan syntax can be validated locally but apply requires live AWS account"
  - test: "Send a customer JWT-authenticated HTTPS request to the ALB DNS name at /servers/echo/mcp and verify a proxied response arrives from the echo ECS task"
    expected: "HTTP 200 from the echo MCP server routed through the gateway; ALB access logs show the request forwarded to the gateway target group"
    why_human: "Requires a live AWS deployment with running ECS tasks and a reachable ALB; cannot simulate ALB routing in unit tests"
---

# Phase 7: AWS Deployment Verification Report

**Phase Goal:** Production-grade AWS infrastructure — ECS Fargate services, RDS PostgreSQL, Secrets Manager, and Cloud Map DNS — deployable via a single terraform apply in the dev environment. Python application extended with ECS adapter and Cloud Map-aware proxy.
**Verified:** 2026-04-20T00:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Terraform bootstrap creates S3 state bucket with KMS encryption and versioning | VERIFIED | `infra/bootstrap/main.tf` contains `aws_s3_bucket` with `prevent_destroy=true`, `aws_s3_bucket_versioning` (Enabled), `aws_s3_bucket_server_side_encryption_configuration` with `sse_algorithm="aws:kms"`, and `aws_s3_bucket_public_access_block` with all four settings true |
| 2 | VPC module produces a private-only VPC with subnets across 2 AZs and all required VPC endpoints | VERIFIED | `infra/modules/vpc/main.tf` has `aws_vpc` with `enable_dns_support=true`, `aws_subnet` with `count=2`, and exactly 8 `aws_vpc_endpoint` resources (s3 gateway + ecr.api, ecr.dkr, ecs, ecs-agent, ecs-telemetry, logs, secretsmanager interface endpoints) |
| 3 | RDS module defines a db.t3.micro PostgreSQL 16 instance in private subnets | VERIFIED | `infra/modules/rds/main.tf` has `aws_db_instance` with `engine="postgres"`, `instance_class=var.instance_class` (default `"db.t3.micro"`), `storage_encrypted=true`, and `aws_db_subnet_group` using `var.private_subnet_ids` |
| 4 | Secrets module creates placeholder secrets for DATABASE_URL, OPERATOR_JWT_SECRET, CUSTOMER_JWT_SECRET | VERIFIED | `infra/modules/secrets/main.tf` has three `aws_secretsmanager_secret` resources, no `aws_secretsmanager_secret_version` (values populated out of band per D-20) |
| 5 | ECR module creates repositories for gateway, admin-api, echo, and ping images | VERIFIED | `infra/modules/ecr/main.tf` has `aws_ecr_repository` with `for_each = toset(var.image_names)`, `image_tag_mutability="IMMUTABLE"`, `scan_on_push=true`, and lifecycle policy keeping last 10 images |
| 6 | ALB module creates an internal load balancer with TLS listener forwarding to a gateway target group | VERIFIED | `infra/modules/alb/main.tf` has `aws_lb` with `internal=true`, `aws_lb_listener` with `port=443`, `protocol="HTTPS"`, `ssl_policy="ELBSecurityPolicy-TLS13-1-2-2021-06"`, and `aws_lb_target_group` with `target_type="ip"` |
| 7 | Cloud Map module creates a private DNS namespace switchboard.local with service entries for echo and ping | VERIFIED | `infra/modules/cloudmap/main.tf` has `aws_service_discovery_private_dns_namespace` with `name=var.namespace_name` (default `"switchboard.local"`) and `aws_service_discovery_service` with `for_each`, `ttl=10`, `failure_threshold=1` |
| 8 | ECS module creates a Fargate cluster with security groups that restrict MCP server ingress to gateway only | VERIFIED | `infra/modules/ecs/main.tf` has `aws_ecs_cluster` with `aws_ecs_cluster_capacity_providers` using `"FARGATE"`. MCP server SG has single ingress rule `referenced_security_group_id = aws_security_group.gateway.id` only — no VPC CIDR or 0.0.0.0/0 ingress rules exist |
| 9 | Dev environment root config composes all modules into a working Terraform plan | VERIFIED | `infra/environments/dev/main.tf` has 7 module blocks (vpc, ecr, secrets, rds, alb, cloudmap, ecs) with explicit cross-module variable wiring. `infra/environments/dev/backend.tf` uses `use_lockfile=true`, `required_version="~> 1.14"`, `hashicorp/aws version="~> 6.0"` |
| 10 | ECS task definitions inject secrets from Secrets Manager ARNs (not plaintext) | VERIFIED | `infra/modules/ecs/services.tf` uses `secrets = [{name=..., valueFrom=var.*_secret_arn}]` blocks on gateway (3 secrets), admin-api (2 secrets), and migration (1 secret) task definitions — no plaintext values in `environment` blocks |
| 11 | Each ECS service has a dedicated task role with least-privilege IAM policy | VERIFIED | `infra/modules/ecs/iam.tf` defines 4 roles: execution (ECR pull, Secrets read, Logs write), gateway-task (CloudMap read, ECS describe), admin-api-task (ECS CRUD, scoped PassRole, ECR read), mcp-server-task (no permissions). Only `ecr:GetAuthorizationToken` uses `Resource="*"` (AWS-mandated account-level action) |
| 12 | ECS adapter calls update_service with desiredCount=1 for start, desiredCount=0 for stop, and forceNewDeployment=True for restart | VERIFIED | `switchboard/container/ecs_adapter.py` has `_update_service_blocking` with `desiredCount=desired_count` (1 for start, 0 for stop) and `_force_deploy_blocking` with `forceNewDeployment=True`. All wrapped in `asyncio.to_thread`. `boto3.client.close()` in finally blocks. 16 unit tests passing |
| 13 | ContainerManager detects ECS environment via ECS_CONTAINER_METADATA_URI and routes to ECS adapter | VERIFIED | `switchboard/container/manager.py` imports `_is_ecs_environment` and has `if _is_ecs_environment():` dispatch in `start()`, `stop()`, and `restart()` routing to `_start_ecs`, `_stop_ecs`, `_restart_ecs` |
| 14 | terraform apply provisions a working stack — gateway, admin API, PostgreSQL (RDS), and reference server tasks — with all ECS services healthy | NEEDS HUMAN | Terraform configuration is structurally complete and all modules are wired. Cannot verify actual provisioning and service health without live AWS credentials and ACM certificate |
| 15 | Customer MCP requests over HTTPS to the ALB DNS name are correctly routed to the matching ECS task | NEEDS HUMAN | Requires a live deployment; cannot simulate ALB routing, Cloud Map DNS resolution, and ECS task networking in automated checks |

**Score:** 13/15 truths verified (2 require human testing; 0 failed)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `infra/bootstrap/main.tf` | S3 state bucket with KMS encryption, versioning, prevent_destroy | VERIFIED | 92 lines, all required resources present |
| `infra/modules/vpc/main.tf` | VPC, private subnets, route tables, 8 VPC endpoints | VERIFIED | 196 lines, 8 endpoints (1 gateway + 7 interface) |
| `infra/modules/rds/main.tf` | RDS PostgreSQL 16 instance in private subnets | VERIFIED | `aws_db_instance` with `engine="postgres"`, `storage_encrypted=true` |
| `infra/modules/secrets/main.tf` | 3 placeholder secrets, no secret_version | VERIFIED | 3 `aws_secretsmanager_secret` resources, zero `aws_secretsmanager_secret_version` |
| `infra/modules/ecr/main.tf` | ECR repositories with IMMUTABLE tags, scan_on_push | VERIFIED | `for_each`, `image_tag_mutability="IMMUTABLE"`, `scan_on_push=true` |
| `infra/modules/alb/main.tf` | Internal ALB with HTTPS listener and gateway target group | VERIFIED | `internal=true`, HTTPS/443 listener, TLS 1.3 policy |
| `infra/modules/cloudmap/main.tf` | Private DNS namespace and service discovery entries | VERIFIED | `switchboard.local` namespace, `for_each` service entries, TTL=10 |
| `infra/modules/ecs/main.tf` | ECS Fargate cluster and security groups | VERIFIED | Fargate cluster + 3 security groups with correct ingress rules |
| `infra/modules/ecs/iam.tf` | 4 IAM roles with least-privilege policies | VERIFIED | 4 roles, scoped policies, no `Resource="*"` except ECR auth |
| `infra/modules/ecs/services.tf` | 5 task definitions, 4 ECS services, Cloud Map registration | VERIFIED | gateway, admin-api, echo, ping services; migration task (no service); service_registries on echo/ping |
| `infra/modules/ecs/logs.tf` | 5 CloudWatch log groups with 30-day retention | VERIFIED | gateway, admin-api, echo, ping, migration — all 30-day retention |
| `infra/environments/dev/main.tf` | Root Terraform config composing all modules | VERIFIED | 7 module blocks with full cross-module variable wiring |
| `infra/environments/dev/backend.tf` | S3 backend with native locking | VERIFIED | `use_lockfile=true`, Terraform 1.14, AWS provider 6.0 |
| `switchboard/container/ecs_adapter.py` | ECSAdapter class with start/stop/restart | VERIFIED | 153 lines (min: 60), `ECSAdapter` class, `_is_ecs_environment` function, `asyncio.to_thread` in all methods |
| `switchboard/container/manager.py` | Updated ContainerManager with ECS detection and dispatch | VERIFIED | `ECS_CONTAINER_METADATA_URI` check present, `_start_ecs/_stop_ecs/_restart_ecs` methods |
| `switchboard/config.py` | Updated Settings with aws_region, ecs_cluster_arn, cloud_map_domain | VERIFIED | All 3 fields present with empty-string defaults |
| `switchboard/gateway/proxy.py` | Updated resolve_backend using cloud_map_domain | VERIFIED | `domain_suffix = settings.cloud_map_domain` appended in URL construction |
| `tests/container/test_ecs_adapter.py` | Unit tests for ECS adapter and environment detection | VERIFIED | 319 lines (min: 80), TestEnvDetection, TestStart, TestStop, TestRestart — 16 tests passing |
| `tests/test_config_ecs.py` | Unit tests for new Settings fields | VERIFIED | 38 lines (min: 20), `test_settings_ecs_defaults` and `test_settings_ecs_values` |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `infra/modules/rds/main.tf` | `infra/modules/vpc/outputs.tf` | `var.private_subnet_ids` | WIRED | `subnet_ids = var.private_subnet_ids` in `aws_db_subnet_group` |
| `infra/modules/vpc/main.tf` | AWS VPC endpoints | Interface endpoints | WIRED | 8 `aws_vpc_endpoint` resources present |
| `infra/modules/alb/main.tf` | `infra/modules/vpc/outputs.tf` | `var.private_subnet_ids` and `var.vpc_id` | WIRED | `subnets = var.private_subnet_ids` in `aws_lb` |
| `infra/modules/cloudmap/main.tf` | `infra/modules/vpc/outputs.tf` | `var.vpc_id` for private DNS namespace | WIRED | `vpc = var.vpc_id` in `aws_service_discovery_private_dns_namespace` |
| `infra/modules/ecs/main.tf` | `infra/modules/alb/outputs.tf` | Security group references for gateway ingress | WIRED | `referenced_security_group_id = var.alb_security_group_id` in gateway ingress rule |
| `infra/environments/dev/main.tf` | `infra/modules/*` | module blocks calling shared modules | WIRED | 7 module blocks with explicit source paths |
| `infra/modules/ecs/services.tf` | `infra/modules/cloudmap/outputs.tf` | `service_registries` referencing Cloud Map ARNs | WIRED | `registry_arn = var.cloudmap_service_arns["sb-echo"]` and `var.cloudmap_service_arns["sb-ping"]` |
| `infra/modules/ecs/services.tf` | `infra/modules/secrets/outputs.tf` | `secrets` block with `valueFrom` ARN references | WIRED | `valueFrom = var.*_secret_arn` pattern on all three secrets across gateway, admin-api, migration task definitions |
| `switchboard/container/manager.py` | `switchboard/container/ecs_adapter.py` | import and instantiation when ECS env detected | WIRED | `from switchboard.container.ecs_adapter import ECSAdapter, _is_ecs_environment` at top-level; adapter created in `_get_ecs_adapter()` |
| `switchboard/gateway/proxy.py` | `switchboard/config.py` | `get_settings().cloud_map_domain` for DNS suffix | WIRED | `settings = get_settings()` then `domain_suffix = settings.cloud_map_domain` in `resolve_backend` |

### Data-Flow Trace (Level 4)

This phase produces Terraform infrastructure definitions (not runtime data-rendering components) and boto3 adapter code. The Python artifacts use settings and environment variables — not dynamic database queries. Level 4 trace applies to the gateway proxy's `cloud_map_domain` usage.

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `switchboard/gateway/proxy.py` | `domain_suffix` (cloud_map_domain) | `get_settings()` → pydantic-settings env var | Yes — reads `CLOUD_MAP_DOMAIN` env var at runtime (empty for Docker, `.switchboard.local` for ECS) | FLOWING |
| `switchboard/container/manager.py` | `_is_ecs_environment()` | `os.environ["ECS_CONTAINER_METADATA_URI"]` | Yes — env var injected by Fargate platform 1.4.0+ at task launch | FLOWING |
| `switchboard/container/ecs_adapter.py` | `cluster_arn`, `region` | `Settings.ecs_cluster_arn`, `Settings.aws_region` | Yes — reads from ECS task environment variables | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| ECS adapter tests pass | `uv run pytest tests/container/test_ecs_adapter.py tests/test_config_ecs.py -x -q` | 16 passed in 0.56s | PASS |
| All container and gateway tests pass | `uv run pytest tests/container/ tests/gateway/ tests/test_config_ecs.py -x -q` | 64 passed in 1.31s | PASS |
| boto3 in pyproject.toml | `grep boto3 pyproject.toml` | `"boto3>=1.42.91"` found | PASS |
| ECS adapter min_lines | `wc -l switchboard/container/ecs_adapter.py` | 153 lines (min: 60) | PASS |
| Test file min_lines | `wc -l tests/container/test_ecs_adapter.py` | 319 lines (min: 80) | PASS |
| No aws_secretsmanager_secret_version in Terraform | `grep -r aws_secretsmanager_secret_version infra/` | Only comment reference, zero resource definitions | PASS |
| 8 VPC endpoints in vpc module | `grep -c aws_vpc_endpoint infra/modules/vpc/main.tf` | 8 | PASS |

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| PLAT-02 | 07-01, 07-02, 07-03, 07-04 | Production deployment targets AWS ECS Fargate with one task per MCP server container | SATISFIED | Terraform modules provision ECS Fargate cluster with separate task definitions for gateway, admin-api, echo, ping, and migration. Python ECS adapter enables the application to manage ECS services at runtime. All 4 plans claim PLAT-02. |

No orphaned requirements found — PLAT-02 is the only requirement mapped to Phase 7 in REQUIREMENTS.md traceability table.

### Anti-Patterns Found

No blocking anti-patterns found.

| File | Pattern | Severity | Notes |
|------|---------|----------|-------|
| `infra/modules/ecs/iam.tf` line 56 | `resources = ["*"]` | Info | Intentional — `ecr:GetAuthorizationToken` is an AWS account-level action that does not support resource scoping per AWS IAM documentation. Documented in code comment and plan decision. Sole exception to the no-wildcard rule. |

### Human Verification Required

#### 1. Terraform Apply — Full Stack Provisioning

**Test:** With AWS credentials configured and `acm_certificate_arn` set in `infra/environments/dev/terraform.tfvars`, run:
```
cd infra/environments/dev
terraform init
terraform apply
```
**Expected:** All resources provision successfully. ECS cluster shows 4 services (gateway, admin-api, echo, ping) with `RUNNING` status and tasks passing health checks. RDS instance reaches `available` state. No Terraform errors.
**Why human:** Requires live AWS account with appropriate IAM permissions, an existing ACM certificate, and a pre-existing S3 state bucket (from `infra/bootstrap/main.tf`). Cannot validate actual cloud provisioning programmatically.

#### 2. End-to-End Request Routing Over HTTPS

**Test:** After `terraform apply` completes, obtain the `alb_dns_name` output. From within the VPC (via Direct Connect or bastion), send an authenticated MCP request:
```
curl -H "Authorization: Bearer <customer_jwt>" \
     https://<alb_dns_name>/servers/echo/mcp \
     -d '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":1}'
```
**Expected:** HTTP 200 response from the echo MCP server, proxied through the gateway. ALB routes HTTPS traffic to gateway on port 8000, gateway resolves `sb-echo.switchboard.local:8000` via Cloud Map, echo task responds.
**Why human:** Requires running ECS tasks, a reachable internal ALB, Cloud Map DNS resolution within the VPC, and valid customer JWT credentials. Cannot simulate AWS networking and service discovery in automated tests.

### Gaps Summary

No gaps found. All 13 programmatically verifiable must-haves pass. The 2 items requiring human verification (SC-1 and SC-2 from ROADMAP.md) depend on live AWS infrastructure that cannot be provisioned in a verification context. The Terraform configuration is structurally complete: all 7 modules exist, are substantive, and are correctly wired through the dev environment root config. The Python application is extended and fully tested (64 passing unit tests with no regressions).

---

_Verified: 2026-04-20T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
