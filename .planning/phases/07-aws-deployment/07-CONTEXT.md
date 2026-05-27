# Phase 7: AWS Deployment - Context

**Gathered:** 2026-04-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Provision the complete Switchboard platform on AWS using Terraform. Deploy all platform components (gateway, admin API, RDS PostgreSQL, reference server ECS services) to a dev environment. All traffic is internal — no public internet exposure. Customers connect via AWS Direct Connect. Phase 7 also adapts the ContainerManager to use ECS APIs (boto3) in production, replacing the Docker SDK backend.

Image CI/CD pipeline (building and pushing images to ECR) is deferred to a future phase. Phase 7 defines ECR repositories in Terraform; image builds are out of scope.

</domain>

<decisions>
## Implementation Decisions

### Infrastructure tooling
- **D-01:** Use **Terraform** (not AWS CDK) for all infrastructure provisioning.
- **D-02:** Remote state stored in S3 + DynamoDB locking (standard AWS Terraform backend). Bootstrap bucket/table separately with a one-time local init.
- **D-03:** `infra/` directory at repo root contains all infrastructure code.
- **D-04:** Directory structure: `infra/environments/dev/` calls shared modules in `infra/modules/`. Phase 7 provisions dev only; `infra/environments/prod/` is stubbed but empty.

### Network topology
- **D-05:** All components run in private VPC subnets — no internet-facing resources. Customers connect via AWS Direct Connect.
- **D-06:** A single **internal Application Load Balancer** (`scheme = internal`) handles TLS termination and routes customer traffic to the gateway ECS service.
- **D-07:** The gateway reaches MCP containers directly within the VPC via **AWS Cloud Map DNS**. Backend URL pattern: `http://sb-{name}.switchboard.local:8000`. Each MCP server ECS service auto-registers with Cloud Map on start.
- **D-08:** MCP server containers run in private subnets with security groups that permit ingress only from the gateway security group (no public port exposure).

### Container management in ECS
- **D-09:** The `ContainerManager` gets an **ECS API adapter** backed by boto3. In production (ECS), start/stop/restart call ECS service APIs instead of Docker SDK.
- **D-10:** `start` = create or update ECS service with `desired_count=1`. `stop` = set `desired_count=0`. `restart` = force new deployment on the existing service.
- **D-11:** Environment routing: detect ECS (e.g., via `ECS_CONTAINER_METADATA_URI` env var) and use ECS adapter; otherwise fall back to Docker SDK. This preserves local Docker Compose development workflow unchanged.
- **D-12:** Each MCP server ECS service is registered with Cloud Map on creation so the gateway can resolve it immediately.

### ECS services
- **D-13:** ECS Fargate launch type for all services (gateway, admin-api, echo, ping).
- **D-14:** Gateway and admin-api ECS services are always running (`desired_count=1`). Reference server services (echo, ping) are pre-deployed and running as fixed services for Phase 7.
- **D-15:** Each ECS service has a task-level IAM role scoped to only what it needs (gateway: Cloud Map read, ECS service describe; admin-api: ECS service create/update/delete, ECR pull; reference servers: minimal — no AWS API access).

### Database
- **D-16:** Amazon RDS PostgreSQL 16, deployed in private subnets. Instance class: `db.t3.micro` for dev.
- **D-17:** Database credentials stored in AWS Secrets Manager. ECS task definitions reference the secret ARN via `secrets:` (not plaintext environment variables).
- **D-18:** Alembic migrations run as a separate ECS run-task during `terraform apply` (via `null_resource` / `local-exec` or a post-deploy script). Not baked into the application container startup.

### Secrets management
- **D-19:** AWS Secrets Manager stores: `DATABASE_URL`, `OPERATOR_JWT_SECRET`, `CUSTOMER_JWT_SECRET`. ECS task definitions inject these as environment variables via `secrets:` block.
- **D-20:** Terraform creates placeholder secrets during provisioning; actual secret values are populated separately (out of band) before services start.

### Image pipeline
- **D-21:** Terraform defines ECR repositories (one per image: gateway, admin-api, echo, ping). Image builds and pushes are **deferred to a CI/CD pipeline** defined in a future phase.
- **D-22:** For Phase 7 validation (`terraform apply` success), images are assumed to be pre-built and pushed to ECR manually. The Terraform plan succeeds even if ECR repos are empty (ECS service creation does not block on image availability at plan time).

### Claude's Discretion
- Exact VPC CIDR ranges and subnet layout
- ALB listener port and certificate handling (ACM certificate ARN as a variable)
- ECS cluster name and capacity provider settings
- Cloud Map namespace name (e.g., `switchboard.local`)
- RDS parameter group and storage configuration details
- Terraform module naming and internal file structure within `infra/`

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` §PLAT-02 — "Production deployment targets AWS ECS Fargate with one task per MCP server container"

### Phase 7 roadmap entry
- `.planning/ROADMAP.md` §Phase 7 — Goal, success criteria, dependency on Phase 6

### Existing application code (integration points)
- `switchboard/container/manager.py` — ContainerManager class to be extended with ECS adapter
- `switchboard/gateway/proxy.py` — `resolve_backend()` function; Cloud Map DNS pattern replaces Docker DNS in production
- `switchboard/config.py` — Settings class; new ECS-specific config vars (cluster ARN, region, Cloud Map namespace) needed
- `Dockerfile` — Multi-target build (gateway, admin-api); used as source for ECR images
- `servers/echo/Dockerfile` and `servers/ping/Dockerfile` — Reference server images for ECR

### Stack decisions
- `CLAUDE.md` §Technology Stack — Recommends ECS + Fargate, ALB, RDS, Secrets Manager, ECR; Terraform listed as a valid alternative to CDK when org uses Terraform for cross-team consistency

No external specs beyond the above — requirements fully captured in decisions above.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `switchboard/container/manager.py` — ContainerManager class; needs ECS adapter method. The Docker adapter stays intact for local development. Pattern: backend detection via env var, then dispatch to Docker or ECS implementation.
- `switchboard/gateway/proxy.py` — `resolve_backend()` returns `http://sb-{name}:8000` today; in ECS this becomes `http://sb-{name}.switchboard.local:8000` (Cloud Map). No logic change needed — just a different hostname format via config.
- `switchboard/config.py` — pydantic-settings `Settings` class; add `aws_region`, `ecs_cluster_arn`, `cloud_map_namespace` (with defaults for local dev where they're unused).
- `Dockerfile` (multi-stage: `gateway` + `admin-api` targets) — ready to push directly to ECR.

### Established Patterns
- `asyncio.to_thread()` for blocking SDK calls (Docker SDK pattern from `ContainerManager`) — apply same pattern to boto3 ECS API calls
- `structlog` JSON logging already configured — Cloud Watch log group can ingest JSON lines directly
- pydantic-settings env var injection — ECS task definitions inject the same env var names Secrets Manager already stores

### Integration Points
- `switchboard/container/manager.py`: Add `_start_ecs_service()`, `_stop_ecs_service()`, `_restart_ecs_service()` methods; dispatch based on `ECS_CONTAINER_METADATA_URI` presence
- `infra/modules/` (new): VPC, ALB, ECS cluster, RDS, Secrets Manager, Cloud Map, ECR modules
- `infra/environments/dev/main.tf` (new): Root Terraform config for the dev environment; calls modules and passes variable values

</code_context>

<specifics>
## Specific Ideas

- Direct Connect assumed to be provisioned externally (not in Phase 7 Terraform scope). The internal ALB VPC attachment is all Phase 7 needs to create.
- `sb-{name}.switchboard.local` Cloud Map hostname pattern maps cleanly to the existing `sb-{server_name}` Docker naming convention — minimal gateway code change.
- ECS adapter detection via `ECS_CONTAINER_METADATA_URI` env var is the standard AWS approach for "am I running in ECS?" without hardcoding.

</specifics>

<deferred>
## Deferred Ideas

- CI/CD pipeline for ECR image builds (GitHub Actions, CodePipeline, etc.) — future phase
- Production environment Terraform (`infra/environments/prod/`) — `dev` first, prod after validation
- Multi-AZ RDS (high availability) — deferred, `db.t3.micro` single-AZ for dev
- Terragrunt for DRY multi-env config — not needed for v1 with two environments
- Per-customer ACLs at the ALB or gateway layer — out of scope per PROJECT.md

</deferred>

---

*Phase: 07-aws-deployment*
*Context gathered: 2026-04-19*
