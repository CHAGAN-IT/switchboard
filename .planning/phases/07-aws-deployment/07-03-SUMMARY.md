---
phase: 07-aws-deployment
plan: 03
subsystem: infra
tags: [terraform, ecs, fargate, iam, cloudwatch, secrets-manager, cloud-map, service-discovery]

# Dependency graph
requires:
  - phase: 07-aws-deployment/01
    provides: "VPC, RDS, Secrets Manager, ECR modules"
  - phase: 07-aws-deployment/02
    provides: "ALB, Cloud Map, ECS cluster with security groups"
provides:
  - "ECS task definitions for gateway, admin-api, echo, ping, and migration"
  - "ECS services for gateway, admin-api, echo, ping with Cloud Map registration"
  - "4 IAM roles with least-privilege policies (execution, gateway-task, admin-api-task, mcp-server-task)"
  - "5 CloudWatch log groups with 30-day retention"
  - "Dev environment root Terraform config composing all 7 modules"
  - "S3 backend with native locking (no DynamoDB)"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Secrets injection via valueFrom ARN references in ECS container_definitions"
    - "Separate execution role (image pull, secrets, logs) from per-service task roles"
    - "Migration as ECS run-task with command override on admin-api image"
    - "Cloud Map service_registries on MCP server ECS services for DNS discovery"

key-files:
  created:
    - infra/modules/ecs/iam.tf
    - infra/modules/ecs/logs.tf
    - infra/modules/ecs/services.tf
    - infra/environments/dev/backend.tf
    - infra/environments/dev/main.tf
    - infra/environments/dev/variables.tf
    - infra/environments/dev/outputs.tf
    - infra/environments/dev/terraform.tfvars
  modified:
    - infra/modules/ecs/variables.tf
    - infra/modules/ecs/outputs.tf

key-decisions:
  - "ecr:GetAuthorizationToken uses Resource='*' as the sole exception to the no-wildcard rule (AWS IAM requirement)"
  - "Admin API ECS service is NOT registered with ALB -- internal-only access within VPC"
  - "Migration task reuses admin-api image with command override rather than a separate image"
  - "S3 native locking (use_lockfile=true) instead of DynamoDB per Terraform 1.14 best practice"

patterns-established:
  - "Dev environment root module pattern: main.tf composes modules, variables.tf defines inputs, outputs.tf surfaces identifiers"
  - "ECS task definition secrets block pattern: { name = ENV_VAR, valueFrom = secret_arn }"
  - "Per-service IAM task roles with scoped iam:PassRole"

requirements-completed: [PLAT-02]

# Metrics
duration: 4min
completed: 2026-04-19
---

# Phase 7 Plan 3: ECS Services and Dev Environment Summary

**ECS task definitions with Secrets Manager injection, 4 least-privilege IAM roles, Cloud Map registration for MCP servers, and dev environment root Terraform config composing all 7 modules**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-19T23:16:56Z
- **Completed:** 2026-04-19T23:21:35Z
- **Tasks:** 2
- **Files created/modified:** 10

## Accomplishments

- Created 4 IAM roles with strict least-privilege policies: shared execution role (ECR pull, Secrets Manager read, CloudWatch write), gateway task role (Cloud Map read, ECS describe), admin-api task role (ECS CRUD, scoped PassRole), MCP server task role (no permissions)
- Created 5 ECS task definitions: gateway, admin-api, echo, ping, and migration (Alembic via run-task)
- Created 4 ECS Fargate services with desired_count=1, Cloud Map registration on echo/ping
- Created 5 CloudWatch log groups with 30-day retention
- Created dev environment root Terraform configuration composing all 7 modules (VPC, ECR, Secrets, RDS, ALB, Cloud Map, ECS)
- S3 backend with native locking (use_lockfile=true) eliminates DynamoDB dependency

## Task Commits

Each task was committed atomically:

1. **Task 1: ECS IAM roles, task definitions, services, and log groups** - `2943464` (feat)
2. **Task 2: Dev environment root Terraform configuration** - `a78b2c6` (feat)

## Files Created/Modified

- `infra/modules/ecs/iam.tf` - 4 IAM roles: execution (ECR+Secrets+Logs), gateway-task (CloudMap+ECS describe), admin-api-task (ECS CRUD+PassRole+ECR read), mcp-server-task (none)
- `infra/modules/ecs/logs.tf` - 5 CloudWatch log groups (gateway, admin-api, echo, ping, migration) with 30-day retention
- `infra/modules/ecs/services.tf` - 5 task definitions and 4 ECS services with Fargate launch type, secrets injection, Cloud Map registration
- `infra/modules/ecs/variables.tf` - Added 8 new variables for subnets, region, ECR URLs/ARNs, secret ARNs, target group, Cloud Map, RDS SG
- `infra/modules/ecs/outputs.tf` - Added migration_task_definition_arn output
- `infra/environments/dev/backend.tf` - S3 backend with native locking, Terraform ~> 1.14, AWS provider ~> 6.0
- `infra/environments/dev/main.tf` - Root config composing all 7 modules with cross-module variable wiring
- `infra/environments/dev/variables.tf` - aws_region, environment, acm_certificate_arn (required), vpc_cidr
- `infra/environments/dev/outputs.tf` - ALB DNS, ECS cluster ARN, ECR URLs, RDS endpoint, migration task ARN
- `infra/environments/dev/terraform.tfvars` - Dev-specific values (us-east-1, dev, 10.0.0.0/16)

## Decisions Made

- **ecr:GetAuthorizationToken wildcard:** The `ecr:GetAuthorizationToken` action is an account-level operation that does not support resource-level scoping per AWS IAM documentation. This is the sole `Resource = "*"` in the IAM policies. All other statements are scoped to specific ARNs.
- **Admin API not on ALB:** The admin API ECS service is internal-only and not registered with the ALB target group. Operators access it within the VPC via Direct Connect, not through the customer-facing ALB.
- **Migration reuses admin-api image:** The migration task definition uses the admin-api container image with a command override (`uv run alembic upgrade head`), avoiding a separate Docker image for migrations (D-18).
- **S3 native locking:** Used `use_lockfile = true` instead of DynamoDB for state locking, which is the current Terraform standard (stable since 1.11+). This simplifies infrastructure and eliminates a DynamoDB table.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] ALB module vpc_cidr_block variable**
- **Found during:** Task 2
- **Issue:** The ALB module requires a `vpc_cidr_block` variable (used for egress rules), but the plan's main.tf example did not include it.
- **Fix:** Added `vpc_cidr_block = module.vpc.vpc_cidr_block` to the ALB module call in main.tf.
- **Files modified:** `infra/environments/dev/main.tf`
- **Commit:** a78b2c6

## Threat Mitigations Verified

| Threat ID | Mitigation | Verified |
|-----------|-----------|----------|
| T-7-10 | 4 separate IAM roles, no `Resource = "*"` except ecr:GetAuthorizationToken (AWS requirement) | Yes |
| T-7-11 | Secrets injected via `secrets` block with `valueFrom` ARN, never plaintext `environment` | Yes |
| T-7-12 | Only admin-api task role has `ecs:UpdateService` / `ecs:CreateService` | Yes |
| T-7-13 | `iam:PassRole` scoped to execution role + MCP server task role ARNs only | Yes |
| T-7-14 | No `aws_secretsmanager_secret_version` resources in any Terraform file | Yes |

## Issues Encountered

None.

## Known Stubs

None -- all infrastructure is fully wired. No placeholder data or TODO markers.

## User Setup Required

Before running `terraform apply` in the dev environment:
1. Set `acm_certificate_arn` in `terraform.tfvars` (request or import an ACM certificate)
2. Ensure the S3 state bucket exists (created by `infra/bootstrap/main.tf`)
3. Push container images to ECR repositories (images can be empty for `terraform plan`)
4. Populate secret values in AWS Secrets Manager (out-of-band per D-20)

## Next Phase Readiness

- Complete dev environment is ready for `terraform plan` (requires AWS credentials and ACM cert ARN)
- After `terraform apply`, run migration via: `aws ecs run-task --task-definition <migration_task_definition_arn>`
- All ECS services will start with `desired_count=1` once container images are pushed to ECR

## Self-Check: PASSED

All 10 created/modified files verified present on disk. Both task commits (2943464, a78b2c6) confirmed in git log.

---
*Phase: 07-aws-deployment*
*Completed: 2026-04-19*
