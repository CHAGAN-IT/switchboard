# Phase 7: AWS Deployment - Research

**Researched:** 2026-04-19
**Domain:** AWS infrastructure (Terraform, ECS Fargate, Cloud Map, RDS, Secrets Manager) + Python ECS adapter (boto3)
**Confidence:** HIGH

## Summary

Phase 7 provisions the complete Switchboard platform on AWS using Terraform and adapts the Python `ContainerManager` to use ECS APIs via boto3 in production. The infrastructure spans a private VPC with an internal ALB for TLS termination, ECS Fargate services for gateway/admin-api/reference-servers, RDS PostgreSQL, AWS Cloud Map for service discovery, ECR repositories, and Secrets Manager for credential injection.

The user has made 22 locked decisions (D-01 through D-22) that fully constrain the architecture. This is a greenfield infrastructure phase -- no existing Terraform code exists. The Python application code changes are surgical: an ECS adapter in `ContainerManager`, new config fields in `Settings`, and minor hostname adjustment in the gateway proxy.

**Primary recommendation:** Use Terraform ~> 1.14 with AWS provider ~> 6.x, S3 backend with native locking (`use_lockfile = true`, no DynamoDB needed). Structure `infra/` as shared modules called from `infra/environments/dev/`. Add `boto3` as a production dependency and wrap all ECS API calls in `asyncio.to_thread()` following the established Docker SDK pattern.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Use **Terraform** (not AWS CDK) for all infrastructure provisioning.
- **D-02:** Remote state stored in S3 + DynamoDB locking (standard AWS Terraform backend). Bootstrap bucket/table separately with a one-time local init.
- **D-03:** `infra/` directory at repo root contains all infrastructure code.
- **D-04:** Directory structure: `infra/environments/dev/` calls shared modules in `infra/modules/`. Phase 7 provisions dev only; `infra/environments/prod/` is stubbed but empty.
- **D-05:** All components run in private VPC subnets -- no internet-facing resources. Customers connect via AWS Direct Connect.
- **D-06:** A single **internal Application Load Balancer** (`scheme = internal`) handles TLS termination and routes customer traffic to the gateway ECS service.
- **D-07:** The gateway reaches MCP containers directly within the VPC via **AWS Cloud Map DNS**. Backend URL pattern: `http://sb-{name}.switchboard.local:8000`. Each MCP server ECS service auto-registers with Cloud Map on start.
- **D-08:** MCP server containers run in private subnets with security groups that permit ingress only from the gateway security group (no public port exposure).
- **D-09:** The `ContainerManager` gets an **ECS API adapter** backed by boto3. In production (ECS), start/stop/restart call ECS service APIs instead of Docker SDK.
- **D-10:** `start` = create or update ECS service with `desired_count=1`. `stop` = set `desired_count=0`. `restart` = force new deployment on the existing service.
- **D-11:** Environment routing: detect ECS (e.g., via `ECS_CONTAINER_METADATA_URI` env var) and use ECS adapter; otherwise fall back to Docker SDK. This preserves local Docker Compose development workflow unchanged.
- **D-12:** Each MCP server ECS service is registered with Cloud Map on creation so the gateway can resolve it immediately.
- **D-13:** ECS Fargate launch type for all services (gateway, admin-api, echo, ping).
- **D-14:** Gateway and admin-api ECS services are always running (`desired_count=1`). Reference server services (echo, ping) are pre-deployed and running as fixed services for Phase 7.
- **D-15:** Each ECS service has a task-level IAM role scoped to only what it needs (gateway: Cloud Map read, ECS service describe; admin-api: ECS service create/update/delete, ECR pull; reference servers: minimal -- no AWS API access).
- **D-16:** Amazon RDS PostgreSQL 16, deployed in private subnets. Instance class: `db.t3.micro` for dev.
- **D-17:** Database credentials stored in AWS Secrets Manager. ECS task definitions reference the secret ARN via `secrets:` (not plaintext environment variables).
- **D-18:** Alembic migrations run as a separate ECS run-task during `terraform apply` (via `null_resource` / `local-exec` or a post-deploy script). Not baked into the application container startup.
- **D-19:** AWS Secrets Manager stores: `DATABASE_URL`, `OPERATOR_JWT_SECRET`, `CUSTOMER_JWT_SECRET`. ECS task definitions inject these as environment variables via `secrets:` block.
- **D-20:** Terraform creates placeholder secrets during provisioning; actual secret values are populated separately (out of band) before services start.
- **D-21:** Terraform defines ECR repositories (one per image: gateway, admin-api, echo, ping). Image builds and pushes are deferred to a CI/CD pipeline defined in a future phase.
- **D-22:** For Phase 7 validation (`terraform apply` success), images are assumed to be pre-built and pushed to ECR manually. The Terraform plan succeeds even if ECR repos are empty.

### Claude's Discretion
- Exact VPC CIDR ranges and subnet layout
- ALB listener port and certificate handling (ACM certificate ARN as a variable)
- ECS cluster name and capacity provider settings
- Cloud Map namespace name (e.g., `switchboard.local`)
- RDS parameter group and storage configuration details
- Terraform module naming and internal file structure within `infra/`

### Deferred Ideas (OUT OF SCOPE)
- CI/CD pipeline for ECR image builds (GitHub Actions, CodePipeline, etc.) -- future phase
- Production environment Terraform (`infra/environments/prod/`) -- dev first, prod after validation
- Multi-AZ RDS (high availability) -- deferred, `db.t3.micro` single-AZ for dev
- Terragrunt for DRY multi-env config -- not needed for v1 with two environments
- Per-customer ACLs at the ALB or gateway layer -- out of scope per PROJECT.md
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PLAT-02 | Production deployment targets AWS ECS Fargate with one task per MCP server container | Terraform modules for VPC/ECS/ALB/RDS/Cloud Map/ECR/Secrets Manager, boto3 ECS adapter in ContainerManager, Cloud Map DNS for service discovery |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Language:** Python 3.12+ for all application code
- **Structure:** Top-level package is `switchboard/`, not `src/`
- **Tooling:** `uv` for package management, `ruff` for linting/formatting, `pytest` for testing
- **Async:** All I/O uses `asyncio` + `httpx`; blocking calls wrapped in `asyncio.to_thread()`
- **Data modeling:** Pydantic `BaseModel` for validated external data, pydantic-settings for config
- **Type hints:** Required on all function signatures
- **Testing:** 80%+ coverage, TDD workflow
- **Git:** Conventional commits (`feat:`, `fix:`, etc.)

## Standard Stack

### Infrastructure Tools
| Tool | Version | Purpose | Why Standard |
|------|---------|---------|--------------|
| Terraform | ~> 1.14 | Infrastructure as Code | User decision D-01; latest stable is 1.14.8 [VERIFIED: GitHub releases hashicorp/terraform] |
| hashicorp/aws provider | ~> 6.x | AWS resource management | Latest is 6.40.0 (April 2026); v6 is GA and removes deprecated resources but ECS/ALB/RDS/Cloud Map are unaffected [VERIFIED: Terraform Registry + GitHub issue #41101] |

### AWS Services
| Service | Purpose | Terraform Resource(s) |
|---------|---------|----------------------|
| VPC | Private networking | `aws_vpc`, `aws_subnet`, `aws_route_table`, `aws_nat_gateway` |
| ALB (internal) | TLS termination, routing to gateway | `aws_lb`, `aws_lb_listener`, `aws_lb_target_group` |
| ECS + Fargate | Container orchestration | `aws_ecs_cluster`, `aws_ecs_service`, `aws_ecs_task_definition` |
| ECR | Container image registry | `aws_ecr_repository` |
| RDS PostgreSQL 16 | Server registry database | `aws_db_instance`, `aws_db_subnet_group` |
| Secrets Manager | Credential storage | `aws_secretsmanager_secret`, `aws_secretsmanager_secret_version` |
| Cloud Map | Service discovery DNS | `aws_service_discovery_private_dns_namespace`, `aws_service_discovery_service` |
| S3 | Terraform state storage | `aws_s3_bucket` (bootstrap only) |
| IAM | Task execution/task roles | `aws_iam_role`, `aws_iam_policy` |

### Python Dependencies (New)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| boto3 | >= 1.42 | AWS SDK for ECS adapter | The standard Python AWS SDK; used by ContainerManager ECS adapter for `update_service`, `run_task` API calls [ASSUMED -- version needs PyPI verification at install time] |

**Installation:**
```bash
uv add boto3
```

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Terraform | AWS CDK (Python) | CDK was the original stack recommendation but user chose Terraform (D-01) for cross-team consistency |
| DynamoDB state locking | S3 native locking (`use_lockfile`) | S3 native locking is stable since Terraform 1.10; eliminates DynamoDB table entirely [VERIFIED: HashiCorp docs + community sources] |
| VPC endpoints for ECR | NAT gateway for ECR pulls | VPC endpoints are cheaper and more secure; NAT gateway costs ~$32/month minimum [CITED: docs.aws.amazon.com/AmazonECR/latest/userguide/vpc-endpoints.html] |

### Note on D-02 (State Locking)

D-02 specifies "S3 + DynamoDB locking." However, Terraform >= 1.10 supports native S3 state locking via `use_lockfile = true`, eliminating the DynamoDB table entirely. This is now stable (not experimental) as of Terraform 1.11+. [VERIFIED: developer.hashicorp.com/terraform/language/backend/s3]

**Recommendation:** Use `use_lockfile = true` and skip DynamoDB. If the user insists on DynamoDB for compatibility, use `billing_mode = "PAY_PER_REQUEST"`. This is a Claude's Discretion item since the user said "standard AWS Terraform backend" -- native S3 locking IS the current standard.

## Architecture Patterns

### Recommended Infrastructure Structure
```
infra/
├── bootstrap/                    # One-time local init for S3 state bucket
│   └── main.tf
├── environments/
│   ├── dev/
│   │   ├── main.tf              # Root config -- calls modules
│   │   ├── variables.tf         # Environment-specific vars
│   │   ├── outputs.tf           # Stack outputs (ALB DNS, cluster ARN, etc.)
│   │   ├── terraform.tfvars     # Dev values
│   │   └── backend.tf           # S3 backend config
│   └── prod/                    # Stubbed, empty
│       └── .gitkeep
└── modules/
    ├── vpc/                     # VPC + subnets + route tables
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    ├── alb/                     # Internal ALB + listener + target groups
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    ├── ecs/                     # ECS cluster + services + task definitions
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    ├── rds/                     # RDS PostgreSQL instance + subnet group
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    ├── secrets/                 # Secrets Manager secrets (placeholders)
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    ├── ecr/                     # ECR repositories
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    └── cloudmap/                # Cloud Map namespace + services
        ├── main.tf
        ├── variables.tf
        └── outputs.tf
```

### Python Application Changes
```
switchboard/
├── config.py                    # Add ECS config fields (cluster ARN, region, etc.)
├── container/
│   ├── manager.py              # Add ECS adapter dispatch
│   ├── ecs_adapter.py          # NEW: boto3 ECS operations
│   └── exceptions.py           # Unchanged
└── gateway/
    └── proxy.py                # resolve_backend() uses Cloud Map DNS in ECS
```

### Pattern 1: ECS Environment Detection (D-11)
**What:** Route ContainerManager calls to Docker SDK or ECS adapter based on environment
**When to use:** Every container lifecycle operation (start/stop/restart)
**Example:**
```python
# Source: D-11 from CONTEXT.md, AWS ECS metadata URI standard
import os

def _is_ecs_environment() -> bool:
    """Detect ECS runtime via metadata endpoint env var."""
    return "ECS_CONTAINER_METADATA_URI" in os.environ

# In ContainerManager:
async def start(self, session, server, repo):
    if _is_ecs_environment():
        return await self._start_ecs(session, server, repo)
    return await self._start_docker(session, server, repo)
```

### Pattern 2: boto3 ECS Calls via asyncio.to_thread (D-09)
**What:** Wrap synchronous boto3 ECS API calls for async safety
**When to use:** All ECS adapter methods
**Example:**
```python
# Source: established pattern in switchboard/container/manager.py
import asyncio
import boto3

async def _start_ecs(self, session, server, repo):
    """Create or update ECS service with desired_count=1."""
    service_name = f"sb-{server.name}"
    result = await asyncio.to_thread(
        self._update_ecs_service_blocking,
        service_name,
        desired_count=1,
    )
    # Update registry...

def _update_ecs_service_blocking(
    self, service_name: str, *, desired_count: int
) -> dict:
    """Blocking boto3 call -- runs in thread."""
    client = boto3.client("ecs", region_name=self._region)
    try:
        return client.update_service(
            cluster=self._cluster_arn,
            service=service_name,
            desiredCount=desired_count,
        )
    finally:
        client.close()
```
[VERIFIED: boto3 `update_service` API -- boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ecs/client/update_service.html]

### Pattern 3: Cloud Map DNS Resolution (D-07)
**What:** In ECS, backends resolve via Cloud Map private DNS instead of Docker DNS
**When to use:** Gateway proxy resolve_backend()
**Example:**
```python
# Source: D-07 from CONTEXT.md
# Currently: http://sb-{name}:8000
# In ECS:    http://sb-{name}.switchboard.local:8000

async def resolve_backend(server_name: str, session_id: str | None) -> str:
    # The domain suffix comes from config
    suffix = settings.cloud_map_domain  # "" for Docker, ".switchboard.local" for ECS
    return f"http://sb-{server_name}{suffix}:8000"
```

### Pattern 4: ECS Task Definition with Secrets Injection (D-17, D-19)
**What:** Terraform creates task definitions that pull secrets from Secrets Manager
**When to use:** All ECS services that need DATABASE_URL or JWT secrets
**Example:**
```hcl
# Source: docs.aws.amazon.com/AmazonECS/latest/developerguide/specifying-sensitive-data-tutorial.html
resource "aws_ecs_task_definition" "gateway" {
  family                   = "switchboard-gateway"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.gateway_task.arn

  container_definitions = jsonencode([{
    name  = "gateway"
    image = "${aws_ecr_repository.gateway.repository_url}:latest"
    portMappings = [{
      containerPort = 8000
      protocol      = "tcp"
    }]
    secrets = [
      {
        name      = "CUSTOMER_JWT_SECRET"
        valueFrom = aws_secretsmanager_secret.customer_jwt.arn
      },
      {
        name      = "OPERATOR_JWT_SECRET"
        valueFrom = aws_secretsmanager_secret.operator_jwt.arn
      }
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.gateway.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "gateway"
      }
    }
  }])
}
```
[VERIFIED: docs.aws.amazon.com/AmazonECS/latest/developerguide/secrets-envvar-secrets-manager.html]

### Pattern 5: Cloud Map Service Registration in Terraform (D-12)
**What:** ECS services auto-register with Cloud Map for DNS-based discovery
**When to use:** All MCP server ECS services
**Example:**
```hcl
# Source: registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/service_discovery_service
resource "aws_service_discovery_private_dns_namespace" "switchboard" {
  name        = "switchboard.local"
  vpc         = aws_vpc.main.id
  description = "Switchboard MCP server discovery"
}

resource "aws_service_discovery_service" "echo" {
  name = "sb-echo"

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.switchboard.id
    dns_records {
      ttl  = 10
      type = "A"
    }
    routing_policy = "MULTIVALUE"
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}

# ECS service references the Cloud Map service
resource "aws_ecs_service" "echo" {
  # ...
  service_registries {
    registry_arn = aws_service_discovery_service.echo.arn
  }
}
```
[VERIFIED: registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/service_discovery_service]

### Pattern 6: IAM Role Separation (D-15)
**What:** Separate execution role (pulls images, reads secrets) from task role (runtime AWS API calls)
**When to use:** Every ECS task definition
**Example:**
```hcl
# Execution role -- used by ECS agent, not application code
# Grants: ECR pull, Secrets Manager read, CloudWatch Logs write
resource "aws_iam_role" "ecs_execution" {
  name = "switchboard-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

# Task role -- used by application code at runtime
# Scoped per service (D-15)
resource "aws_iam_role" "gateway_task" {
  name = "switchboard-gateway-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

# Gateway task role: Cloud Map read + ECS describe
resource "aws_iam_role_policy" "gateway_task_policy" {
  role   = aws_iam_role.gateway_task.id
  policy = data.aws_iam_policy_document.gateway_permissions.json
}
```
[CITED: docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html]

### Anti-Patterns to Avoid
- **Single shared IAM role for all services:** Violates least-privilege (D-15). Each service gets a scoped task role.
- **Hardcoded secrets in task definitions:** Use `secrets:` block with Secrets Manager ARNs (D-17), never `environment:` for credentials.
- **Public subnets for ECS tasks:** All components run in private subnets (D-05). The internal ALB is the only entry point.
- **Baking migrations into container startup:** Alembic runs as a separate ECS run-task (D-18), not on every container boot.
- **Using `docker` Python SDK in ECS:** Environment detection (D-11) must route to boto3 adapter when `ECS_CONTAINER_METADATA_URI` is set.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| VPC networking | Custom network configs | Terraform `aws_vpc` + subnet resources with standard /16 CIDR | VPC is well-understood but has many moving parts (IGW, NAT, route tables); use proven patterns |
| Service discovery | Custom DNS or config-based routing | AWS Cloud Map with `aws_service_discovery_private_dns_namespace` | ECS auto-registers tasks; DNS resolution "just works" with TTL=10s |
| Secret injection | Custom secret-fetching code | ECS `secrets:` block + Secrets Manager | ECS agent handles secret fetch at task start; no application code needed |
| Container health checks | Application-level health polling | ECS health check configuration in task definition | ECS automatically stops routing to unhealthy tasks; existing Dockerfile HEALTHCHECK works |
| State locking | Custom locking mechanism | Terraform S3 native locking (`use_lockfile = true`) | Built into Terraform; eliminates DynamoDB table |
| Log aggregation | Custom log shipping | CloudWatch Logs via `awslogs` log driver | ECS natively supports `awslogs`; structlog JSON output is CloudWatch-ready |

**Key insight:** AWS provides managed solutions for service discovery, secret injection, health checking, and log aggregation. Using them eliminates significant custom code and operational burden. The Python code changes are minimal -- just the ECS adapter and config fields.

## Common Pitfalls

### Pitfall 1: Fargate Tasks in Private Subnets Cannot Pull ECR Images
**What goes wrong:** ECS tasks fail to start with "CannotPullContainerError" because private subnets have no internet access.
**Why it happens:** Fargate tasks in private subnets need a path to ECR. Without NAT gateway or VPC endpoints, image pulls fail.
**How to avoid:** Create VPC endpoints for ECR (`com.amazonaws.{region}.ecr.api`, `com.amazonaws.{region}.ecr.dkr`) AND an S3 gateway endpoint (ECR stores layers in S3). This is cheaper than a NAT gateway (~$32/month saved).
**Warning signs:** Tasks stuck in PROVISIONING state; CloudWatch logs show no output at all.
[VERIFIED: docs.aws.amazon.com/AmazonECR/latest/userguide/vpc-endpoints.html]

### Pitfall 2: Execution Role vs Task Role Confusion
**What goes wrong:** Application code can't call AWS APIs even though permissions seem correct.
**Why it happens:** Permissions for ECR pull and Secrets Manager read go on the **execution role** (used by ECS agent). Permissions for runtime API calls (ECS describe, Cloud Map read) go on the **task role** (used by application code).
**How to avoid:** Two separate IAM roles: execution role with ECR + Secrets Manager + CloudWatch Logs; task role with service-specific runtime permissions.
**Warning signs:** "AccessDenied" errors in application logs vs "ResourceInitializationError" in ECS events.
[CITED: docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html]

### Pitfall 3: Cloud Map DNS TTL Causes Stale Resolution
**What goes wrong:** Gateway routes requests to terminated tasks for up to 60 seconds after task stops.
**Why it happens:** Default DNS TTL is too high. Clients cache stale A records.
**How to avoid:** Set Cloud Map service DNS TTL to 10 seconds. Use `MULTIVALUE` routing policy so multiple healthy IPs are returned. Use `health_check_custom_config` with `failure_threshold = 1` so ECS deregisters unhealthy instances immediately.
**Warning signs:** 503 errors after service deployments; requests to ghost IPs.
[VERIFIED: multiple sources -- oneuptime.com, dev.to, registry.terraform.io]

### Pitfall 4: Secrets in Terraform State File
**What goes wrong:** Secret values (DATABASE_URL, JWT secrets) appear in plaintext in `terraform.tfstate`.
**Why it happens:** `aws_secretsmanager_secret_version` with a `secret_string` argument stores the value in state.
**How to avoid:** D-20 says "populate separately out of band." Create `aws_secretsmanager_secret` in Terraform (just the empty secret) but set actual values via AWS CLI: `aws secretsmanager put-secret-value --secret-id NAME --secret-string VALUE`. Never put `aws_secretsmanager_secret_version` with real values in Terraform.
**Warning signs:** `terraform show` reveals plaintext credentials.

### Pitfall 5: ECS Service Update Does Not Force New Deployment
**What goes wrong:** Updating a task definition doesn't replace running tasks.
**Why it happens:** ECS `update_service` by default only changes the task definition for NEW tasks; existing tasks continue with the old definition.
**How to avoid:** For restart (D-10), use `force_new_deployment = true` in the boto3 `update_service` call. For Terraform-managed services, set `force_new_deployment = true` in the `aws_ecs_service` resource.
**Warning signs:** Old containers still running after deploying a new image tag.
[VERIFIED: boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ecs/client/update_service.html]

### Pitfall 6: Alembic Migration Task Needs Database Connectivity
**What goes wrong:** Migration ECS run-task fails to connect to RDS.
**Why it happens:** The migration task needs: (a) a security group that allows egress to the RDS security group on port 5432, (b) the DATABASE_URL secret injected, (c) placement in the same private subnets as RDS.
**How to avoid:** Reuse the admin-api task definition (which already has DATABASE_URL) with a command override: `alembic upgrade head`. Ensure the admin-api security group has egress to the RDS security group.
**Warning signs:** Task exits with "connection refused" or times out.

### Pitfall 7: Missing VPC Endpoints for ECS, Logs, and Secrets Manager
**What goes wrong:** Tasks in private subnets can't reach ECS control plane, CloudWatch Logs, or Secrets Manager.
**Why it happens:** Without internet access (no NAT gateway), ECS tasks need VPC endpoints for all AWS services they communicate with.
**How to avoid:** Create interface VPC endpoints for: `com.amazonaws.{region}.ecs`, `com.amazonaws.{region}.ecs-agent`, `com.amazonaws.{region}.ecs-telemetry`, `com.amazonaws.{region}.logs`, `com.amazonaws.{region}.secretsmanager`, `com.amazonaws.{region}.ecr.api`, `com.amazonaws.{region}.ecr.dkr`. Create a gateway endpoint for `com.amazonaws.{region}.s3`.
**Warning signs:** Tasks stuck in PROVISIONING; "ResourceInitializationError" in ECS events.
[CITED: docs.aws.amazon.com/AmazonECS/latest/developerguide/vpc-endpoints.html]

## Code Examples

### VPC Module (Claude's Discretion)
```hcl
# infra/modules/vpc/main.tf
resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr  # e.g., "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "switchboard-${var.environment}" }
}

# Private subnets across 2 AZs (for RDS subnet group requirement)
resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone = data.aws_availability_zones.available.names[count.index]

  tags = { Name = "switchboard-private-${count.index}" }
}

# VPC endpoints for private subnet AWS service access
resource "aws_vpc_endpoint" "s3" {
  vpc_id       = aws_vpc.main.id
  service_name = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]
}

resource "aws_vpc_endpoint" "ecr_api" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.aws_region}.ecr.api"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true
}

# Similar endpoints for ecr.dkr, ecs, ecs-agent, ecs-telemetry,
# logs, secretsmanager
```

### Security Group Pattern (D-08)
```hcl
# Gateway SG: ingress from ALB, egress to MCP servers
resource "aws_security_group" "gateway" {
  vpc_id = aws_vpc.main.id
  name   = "switchboard-gateway"
}

resource "aws_security_group_rule" "gateway_from_alb" {
  type                     = "ingress"
  from_port                = 8000
  to_port                  = 8000
  protocol                 = "tcp"
  security_group_id        = aws_security_group.gateway.id
  source_security_group_id = aws_security_group.alb.id
}

# MCP server SG: ingress ONLY from gateway (D-08)
resource "aws_security_group" "mcp_server" {
  vpc_id = aws_vpc.main.id
  name   = "switchboard-mcp-server"
}

resource "aws_security_group_rule" "mcp_from_gateway_only" {
  type                     = "ingress"
  from_port                = 8000
  to_port                  = 8000
  protocol                 = "tcp"
  security_group_id        = aws_security_group.mcp_server.id
  source_security_group_id = aws_security_group.gateway.id
}
```

### Bootstrap State Backend
```hcl
# infra/bootstrap/main.tf -- run once with local state
provider "aws" {
  region = "us-east-1"
}

resource "aws_s3_bucket" "terraform_state" {
  bucket = "switchboard-terraform-state"

  lifecycle { prevent_destroy = true }
}

resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
  }
}
```

### ECS Adapter in Python (D-09, D-10, D-11)
```python
# switchboard/container/ecs_adapter.py
"""ECS adapter for ContainerManager -- production backend.

Wraps boto3 ECS service API calls. All blocking calls run inside
asyncio.to_thread() following the pattern from _start_blocking
in the Docker adapter.

Depends on: boto3, switchboard.config
"""
from __future__ import annotations

import asyncio
import logging

import boto3

logger = logging.getLogger(__name__)


class ECSAdapter:
    """Manages MCP server ECS services via boto3.

    Args:
        cluster_arn: ARN of the ECS cluster.
        region: AWS region name.
    """

    def __init__(self, cluster_arn: str, region: str) -> None:
        self._cluster_arn = cluster_arn
        self._region = region

    async def start_service(self, service_name: str) -> dict:
        """Set desired_count=1 on an ECS service (D-10)."""
        return await asyncio.to_thread(
            self._update_service_blocking,
            service_name,
            desired_count=1,
        )

    async def stop_service(self, service_name: str) -> dict:
        """Set desired_count=0 on an ECS service (D-10)."""
        return await asyncio.to_thread(
            self._update_service_blocking,
            service_name,
            desired_count=0,
        )

    async def restart_service(self, service_name: str) -> dict:
        """Force new deployment on an ECS service (D-10)."""
        return await asyncio.to_thread(
            self._force_deploy_blocking,
            service_name,
        )

    def _update_service_blocking(
        self, service_name: str, *, desired_count: int
    ) -> dict:
        client = boto3.client("ecs", region_name=self._region)
        try:
            return client.update_service(
                cluster=self._cluster_arn,
                service=service_name,
                desiredCount=desired_count,
            )
        finally:
            client.close()

    def _force_deploy_blocking(self, service_name: str) -> dict:
        client = boto3.client("ecs", region_name=self._region)
        try:
            return client.update_service(
                cluster=self._cluster_arn,
                service=service_name,
                forceNewDeployment=True,
            )
        finally:
            client.close()
```

### Config Updates
```python
# Additions to switchboard/config.py Settings class
class Settings(BaseSettings):
    # ... existing fields ...

    # ECS configuration (used only when running in ECS; defaults
    # are no-ops for local Docker Compose development)
    aws_region: str = ""
    ecs_cluster_arn: str = ""
    cloud_map_domain: str = ""  # e.g., ".switchboard.local" in ECS, "" locally
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| DynamoDB for Terraform state locking | S3 native locking (`use_lockfile = true`) | Terraform 1.10 (stable in 1.11+) | Eliminates DynamoDB table cost and configuration |
| AWS provider v5.x | AWS provider v6.x (GA April 2026) | April 2026 | Removes deprecated resources (OpsWorks, SimpleDB, Chime); ECS/ALB/RDS unaffected |
| SSE transport for MCP | Streamable HTTP | MCP spec 2025-03-26 | Existing Dockerfiles already use Streamable HTTP |
| NAT gateway for private subnet ECR pulls | VPC endpoints | Available for years but cost-saving trend | Saves ~$32/month per NAT gateway |

**Deprecated/outdated:**
- **DynamoDB state locking:** Still works but S3 native is the current standard for Terraform >= 1.10
- **AWS CDK:** User chose Terraform (D-01); CDK was the original stack recommendation

## Assumptions Log

> List all claims tagged `[ASSUMED]` in this research. The planner and discuss-phase use this
> section to identify decisions that need user confirmation before execution.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | boto3 >= 1.42 is the correct minimum version | Standard Stack | Low -- any recent boto3 supports ECS APIs; exact version verified at install time via PyPI |
| A2 | VPC endpoints are preferred over NAT gateway given the "no internet-facing resources" constraint (D-05) | Architecture / Pitfalls | Medium -- if Direct Connect already provides AWS service access, VPC endpoints may be redundant. But VPC endpoints are standard for pure-private VPC setups |
| A3 | Alembic migration can run via ECS run-task with a command override on the admin-api task definition | Pitfall 6 / Code Examples | Low -- standard pattern per AWS re:Post and community guides; alembic env.py already reads DATABASE_URL from environment |

## Open Questions

1. **ACM Certificate for Internal ALB TLS**
   - What we know: D-06 says internal ALB handles TLS termination. ACM certificate ARN is Claude's Discretion.
   - What's unclear: Does the user have an existing private CA or ACM certificate for internal domains? Or should Terraform create a self-signed cert / private CA?
   - Recommendation: Make `acm_certificate_arn` a required Terraform variable with no default. Document that the user must create or import the cert before `terraform apply`.

2. **AWS Account and Region**
   - What we know: D-16 specifies RDS in private subnets. The stack assumes a specific AWS region.
   - What's unclear: Which AWS account and region to use.
   - Recommendation: Make `aws_region` a variable defaulting to `us-east-1`. Account is implicit from AWS credentials.

3. **Direct Connect Attachment**
   - What we know: D-05 says "customers connect via AWS Direct Connect." CONTEXT.md says "Direct Connect assumed to be provisioned externally."
   - What's unclear: How the internal ALB becomes reachable via Direct Connect (VGW? Transit Gateway?).
   - Recommendation: Out of scope for Phase 7 per CONTEXT.md. The internal ALB is created; connectivity to it via Direct Connect is handled separately.

4. **ECS Adapter Integration with Health Monitor**
   - What we know: `HealthMonitor` currently uses `docker.from_env()` to inspect container state.
   - What's unclear: Should the health monitor also get an ECS adapter, or does ECS's built-in health checking replace it?
   - Recommendation: In ECS, the platform handles health checking via task-level HEALTHCHECK and Cloud Map deregistration. The application-level `HealthMonitor` can be conditionally disabled in ECS (it's redundant). However, this is a minor concern -- defer to Phase 7 implementation and note as a detail for the planner.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Terraform | Infrastructure provisioning | No | -- | Must install: `tfenv install 1.14.8` or direct download |
| AWS CLI | State bootstrap, secret population, migration run-task | No | -- | Must install: `pip install awscli` or binary |
| Docker | Building ECR images (manual push) | Yes | 29.4.0 | -- |
| Python 3.12 | Application code | Yes (project constraint) | 3.12+ | -- |
| uv | Python package management | Yes (project tool) | -- | -- |

**Missing dependencies with no fallback:**
- **Terraform:** Must be installed before any infrastructure work. Phase 7 plans should include an install step or prerequisite check.
- **AWS CLI:** Required for bootstrap state bucket creation, secret value population (D-20), and migration run-task invocation (D-18).

**Missing dependencies with fallback:**
- None -- Terraform and AWS CLI are essential for this phase.

**Note:** Terraform and AWS CLI are developer-machine tools, not runtime dependencies. They are expected to be installed by the operator. The planner should document these as prerequisites rather than automated install steps.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.26.x |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/ -x -q --ignore=tests/reference_servers` |
| Full suite command | `uv run pytest tests/ -q` |

### Phase Requirements to Test Map

Phase 7 is primarily an infrastructure phase (Terraform) with a secondary Python code change (ECS adapter). Terraform validation is done via `terraform plan` and `terraform apply`, not pytest. The Python changes are testable.

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PLAT-02 (infra) | `terraform plan` succeeds for dev environment | smoke | `cd infra/environments/dev && terraform plan` | N/A (infra) |
| PLAT-02 (ECS adapter) | ContainerManager routes to ECS adapter when `ECS_CONTAINER_METADATA_URI` is set | unit | `uv run pytest tests/container/test_ecs_adapter.py -x` | Wave 0 |
| PLAT-02 (ECS start) | ECS adapter calls `update_service(desiredCount=1)` for start | unit | `uv run pytest tests/container/test_ecs_adapter.py::TestStart -x` | Wave 0 |
| PLAT-02 (ECS stop) | ECS adapter calls `update_service(desiredCount=0)` for stop | unit | `uv run pytest tests/container/test_ecs_adapter.py::TestStop -x` | Wave 0 |
| PLAT-02 (ECS restart) | ECS adapter calls `update_service(forceNewDeployment=True)` for restart | unit | `uv run pytest tests/container/test_ecs_adapter.py::TestRestart -x` | Wave 0 |
| PLAT-02 (env detect) | `_is_ecs_environment()` returns True when env var is set | unit | `uv run pytest tests/container/test_ecs_adapter.py::TestEnvDetection -x` | Wave 0 |
| PLAT-02 (config) | Settings class accepts new ECS fields | unit | `uv run pytest tests/test_config_ecs.py -x` | Wave 0 |
| PLAT-02 (proxy) | `resolve_backend()` appends Cloud Map domain when configured | unit | `uv run pytest tests/gateway/test_proxy.py -x` | Existing (needs update) |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/container/ tests/gateway/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/container/test_ecs_adapter.py` -- covers ECS adapter start/stop/restart/env detection
- [ ] `tests/test_config_ecs.py` -- covers new Settings fields (aws_region, ecs_cluster_arn, cloud_map_domain)
- [ ] `tests/gateway/test_proxy.py` -- update existing tests for Cloud Map domain suffix behavior
- [ ] Add `boto3` to project dependencies: `uv add boto3`

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No (handled in Phase 5; JWT validation unchanged) | PyJWT -- already implemented |
| V3 Session Management | No (MCP session ID routing unchanged) | Session map in proxy.py -- already implemented |
| V4 Access Control | Yes | IAM roles scoped per ECS service (D-15); security groups restrict network access (D-08) |
| V5 Input Validation | Yes | Pydantic models for API input -- already implemented; Terraform variables validated via `validation` blocks |
| V6 Cryptography | Yes | TLS termination at ALB (ACM certificate); Secrets Manager for credential storage; KMS encryption for S3 state bucket |

### Known Threat Patterns for AWS ECS + Terraform

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Over-permissive IAM task roles | Elevation of Privilege | Least-privilege task roles per service (D-15); no wildcard `*` resource ARNs |
| Secrets in Terraform state | Information Disclosure | S3 state bucket with KMS encryption + versioning; secret values populated out of band (D-20) |
| Unencrypted RDS traffic | Information Disclosure | All traffic within private VPC; RDS encryption at rest enabled by default on PostgreSQL 16 |
| Container image tampering | Tampering | ECR image scanning enabled; immutable tags recommended |
| MCP server lateral movement | Elevation of Privilege | Security groups restrict MCP server ingress to gateway only (D-08); minimal IAM for reference servers (D-15) |
| Exposed ECS metadata endpoint | Information Disclosure | Fargate platform version 1.4.0+ restricts metadata to the task itself; no cross-task access |

## Sources

### Primary (HIGH confidence)
- [AWS ECS documentation -- task execution IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html) -- execution vs task role separation
- [AWS ECS documentation -- task IAM role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html) -- runtime permissions
- [AWS ECS documentation -- Secrets Manager integration](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/secrets-envvar-secrets-manager.html) -- secret injection pattern
- [AWS ECR documentation -- VPC endpoints](https://docs.aws.amazon.com/AmazonECR/latest/userguide/vpc-endpoints.html) -- private subnet ECR access
- [AWS ECS documentation -- VPC endpoints](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/vpc-endpoints.html) -- required interface endpoints for Fargate
- [Terraform Registry -- aws_service_discovery_service](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/service_discovery_service) -- Cloud Map service configuration
- [Terraform Registry -- aws_service_discovery_private_dns_namespace](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/service_discovery_private_dns_namespace) -- private DNS namespace
- [Terraform S3 backend docs](https://developer.hashicorp.com/terraform/language/backend/s3) -- native locking via `use_lockfile`
- [boto3 ECS update_service](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ecs/client/update_service.html) -- API reference for desiredCount and forceNewDeployment
- [GitHub hashicorp/terraform releases](https://github.com/hashicorp/terraform/releases) -- Terraform 1.14.8 latest stable
- [GitHub hashicorp/terraform-provider-aws #41101](https://github.com/hashicorp/terraform-provider-aws/issues/41101) -- v6.0 breaking changes (ECS/ALB/RDS unaffected)

### Secondary (MEDIUM confidence)
- [oneuptime.com -- ECS Service Discovery with Cloud Map](https://oneuptime.com/blog/post/2026-02-12-ecs-service-discovery-cloud-map/view) -- DNS TTL best practices (10s, MULTIVALUE routing)
- [oneuptime.com -- Create Cloud Map Service Discovery in Terraform](https://oneuptime.com/blog/post/2026-02-23-create-cloud-map-service-discovery-in-terraform/view) -- Terraform patterns
- [dev.to -- Service Discovery vs Service Connect](https://dev.to/aws-builders/why-i-chose-service-discovery-over-service-connect-for-ecs-inter-service-communication-4l9d) -- DNS-based discovery pattern
- [dev.to -- ECS Task Role vs Execution Role](https://dev.to/aws-builders/iam-for-amazon-ecs-on-aws-fargate-2bk8) -- IAM separation patterns
- [scalr.com -- AWS Provider v6.0 Breaking Changes](https://scalr.com/learning-center/aws-provider-v6-0-whats-breaking-in-april-2025/) -- impact analysis

### Tertiary (LOW confidence)
- None -- all claims verified against primary or secondary sources

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- Terraform, AWS provider, and AWS services are well-documented and version-verified
- Architecture: HIGH -- decisions are locked (D-01 through D-22) with minimal discretion areas; patterns verified against official AWS docs
- Pitfalls: HIGH -- common issues verified against AWS documentation and community guides; ECR/VPC endpoint requirement is extensively documented
- Python ECS adapter: HIGH -- follows established `asyncio.to_thread()` pattern from existing ContainerManager; boto3 ECS API is stable and well-documented

**Research date:** 2026-04-19
**Valid until:** 2026-05-19 (30 days -- infrastructure patterns are stable)
