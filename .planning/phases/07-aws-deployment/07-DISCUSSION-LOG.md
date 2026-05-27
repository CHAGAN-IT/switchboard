# Phase 7: AWS Deployment - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-19
**Phase:** 07-aws-deployment
**Areas discussed:** Dynamic container management, Service discovery approach, CDK project structure, Image pipeline

---

## Dynamic container management

| Option | Description | Selected |
|--------|-------------|----------|
| Static services only | Phase 7 deploys echo and ping as fixed ECS services. Admin API lifecycle not wired to ECS. | |
| ECS API adapter (full) | ContainerManager gets a boto3-backed ECS adapter alongside Docker backend | ✓ |
| ECS run-task (ephemeral) | Each start call uses ECS RunTask; no persistent service | |

**Follow-up: When operator calls start, what happens?**

| Option | Description | Selected |
|--------|-------------|----------|
| Create/update ECS service | `desired_count=1`. Stop = `desired_count=0`. Restart = force deploy. | ✓ |
| RunTask per call | Ephemeral task, no auto-recovery | |

**User's choice:** Full ECS API adapter; start/stop/restart map to ECS service desired_count management.

---

## Service discovery approach

**Initial: How does the gateway route to MCP containers in ECS?**

| Option | Description | Selected |
|--------|-------------|----------|
| AWS Cloud Map DNS | `http://sb-{name}.switchboard.local:8000` | ✓ (after clarification) |
| ECS Service Connect | Proxy mesh, built-in observability | |
| Internal ALB path routing | Gateway calls internal ALB | Initially selected, then refined |

**User clarification:** Traffic should be entirely internal, no public exposure. Direct Connect is assumed.

**Refined question: Network topology with Direct Connect?**

| Option | Description | Selected |
|--------|-------------|----------|
| Internal ALB in private subnets | scheme=internal, TLS, Direct Connect access | ✓ |
| VPC endpoint / PrivateLink | More complex network isolation | |

**User question:** "Why would we need two load balancers? Can't one load balancer do all the routing?"
**Resolution:** Correct — one internal ALB routes to the gateway. Gateway then contacts MCP containers directly via Cloud Map DNS. No second ALB needed.

**Final decisions:**
- Single internal ALB → gateway ECS service
- Gateway → MCP containers via Cloud Map DNS (`http://sb-{name}.switchboard.local:8000`)

---

## CDK project structure (became: Terraform)

| Option | Description | Selected |
|--------|-------------|----------|
| infra/ at repo root | CDK entry in `infra/`, shared modules | ✓ (location) |
| cdk/ at repo root | Same concept, different name | |
| Separate repo | Infrastructure in dedicated Git repo | |

**User clarification:** Use **Terraform** instead of CDK. Environments should be separated.

**Follow-up: Terraform environment organization?**

| Option | Description | Selected |
|--------|-------------|----------|
| Separate directories per env | `infra/environments/dev/`, `infra/environments/prod/` calling `infra/modules/` | ✓ |
| Terraform workspaces | Single config, workspace per env | |
| Terragrunt | DRY wrapper over Terraform | |

**Follow-up: Environments in scope for Phase 7?**

| Option | Description | Selected |
|--------|-------------|----------|
| dev only | Phase 7 provisions dev; prod is a future concern | ✓ |
| dev + prod | Both environments in Phase 7 | |

---

## Image pipeline

**ECR image strategy?**

| Option | Description | Selected |
|--------|-------------|----------|
| Manual build+push script | `scripts/push-images.sh` before `terraform apply` | |
| Terraform null_resource / local-exec | Builds run as part of apply | |
| Deferred to CI/CD | ECR repos in Terraform; builds in future CI pipeline | ✓ |

**Terraform state backend?**

| Option | Description | Selected |
|--------|-------------|----------|
| S3 + DynamoDB locking | Standard AWS remote state | ✓ |
| Local state | Simple but not shareable | |

---

## Claude's Discretion

- VPC CIDR ranges and subnet layout
- ALB listener port and certificate handling
- ECS cluster name and capacity provider settings
- Cloud Map namespace name
- RDS parameter group and storage details
- Terraform module naming and internal file structure

## Deferred Ideas

- CI/CD pipeline for ECR image builds — future phase
- Production environment (`infra/environments/prod/`) — after dev validated
- Multi-AZ RDS — deferred, single-AZ for dev
- Terragrunt for DRY multi-env config — not needed for v1
