---
phase: 07-aws-deployment
reviewed: 2026-04-20T00:00:00Z
depth: standard
files_reviewed: 38
files_reviewed_list:
  - infra/bootstrap/main.tf
  - infra/environments/dev/backend.tf
  - infra/environments/dev/main.tf
  - infra/environments/dev/outputs.tf
  - infra/environments/dev/terraform.tfvars
  - infra/environments/dev/variables.tf
  - infra/modules/alb/main.tf
  - infra/modules/alb/outputs.tf
  - infra/modules/alb/variables.tf
  - infra/modules/cloudmap/main.tf
  - infra/modules/cloudmap/outputs.tf
  - infra/modules/cloudmap/variables.tf
  - infra/modules/ecr/main.tf
  - infra/modules/ecr/outputs.tf
  - infra/modules/ecr/variables.tf
  - infra/modules/ecs/iam.tf
  - infra/modules/ecs/logs.tf
  - infra/modules/ecs/main.tf
  - infra/modules/ecs/outputs.tf
  - infra/modules/ecs/services.tf
  - infra/modules/ecs/variables.tf
  - infra/modules/rds/main.tf
  - infra/modules/rds/outputs.tf
  - infra/modules/rds/variables.tf
  - infra/modules/secrets/main.tf
  - infra/modules/secrets/outputs.tf
  - infra/modules/secrets/variables.tf
  - infra/modules/vpc/main.tf
  - infra/modules/vpc/outputs.tf
  - infra/modules/vpc/variables.tf
  - pyproject.toml
  - switchboard/config.py
  - switchboard/container/ecs_adapter.py
  - switchboard/container/manager.py
  - switchboard/gateway/proxy.py
  - tests/container/test_ecs_adapter.py
  - tests/container/test_manager.py
  - tests/gateway/test_proxy.py
  - tests/test_config_ecs.py
findings:
  critical: 2
  warning: 6
  info: 5
  total: 13
status: issues_found
---

# Phase 7: Code Review Report

**Reviewed:** 2026-04-20
**Depth:** standard
**Files Reviewed:** 38
**Status:** issues_found

## Summary

This phase introduces the full AWS deployment stack: Terraform modules for VPC, ECR, ECS, RDS, Secrets Manager, ALB, and Cloud Map; Python ECS adapter and updated container manager; updated gateway proxy for ECS Cloud Map routing; and corresponding tests.

The overall design is well-structured and security-conscious. The least-privilege IAM approach, immutable ECR tags, secrets injected via `valueFrom`, and the network isolation of MCP server containers behind the gateway security group are all strong. However, there are two critical bugs in the IAM module that will cause runtime failures: ECS resource ARNs are constructed incorrectly (the `cluster-arn/*` wildcard does not match service or task ARNs), and the `:latest` image tag collides with immutable ECR enforcement. Four additional warnings address correctness gaps in state management and header forwarding.

---

## Critical Issues

### CR-01: ECS IAM Resource ARN Pattern Does Not Match Service or Task ARNs

**File:** `infra/modules/ecs/iam.tf:126` and `infra/modules/ecs/iam.tf:165`
**Issue:** Both the gateway task role and the admin API task role use `"${aws_ecs_cluster.main.arn}/*"` as the resource for ECS service and task actions. ECS service ARNs take the form `arn:aws:ecs:REGION:ACCOUNT:service/CLUSTER-NAME/SERVICE-NAME`, not `arn:aws:ecs:REGION:ACCOUNT:cluster/CLUSTER-NAME/*`. This ARN pattern mismatch will cause IAM authorization failures silently at runtime: the policy exists and validates during `terraform apply`, but AWS will deny `ecs:DescribeServices`, `ecs:DescribeTasks`, `ecs:CreateService`, `ecs:UpdateService`, `ecs:DeleteService`, `ecs:RunTask`, and `ecs:RegisterTaskDefinition` because none of those resource ARNs match the cluster ARN wildcard.

**Fix:**
```hcl
# In data "aws_iam_policy_document" "gateway_task" (line ~119-127):
statement {
  sid = "ECSDescribe"
  actions = [
    "ecs:DescribeServices",
    "ecs:DescribeTasks",
  ]
  resources = [
    "arn:aws:ecs:*:*:service/${aws_ecs_cluster.main.name}/*",
    "arn:aws:ecs:*:*:task/${aws_ecs_cluster.main.name}/*",
  ]
}

# In data "aws_iam_policy_document" "admin_api_task" (line ~151-166):
statement {
  sid = "ECSManage"
  actions = [
    "ecs:CreateService",
    "ecs:UpdateService",
    "ecs:DeleteService",
    "ecs:DescribeServices",
    "ecs:DescribeTasks",
    "ecs:RegisterTaskDefinition",
    "ecs:DeregisterTaskDefinition",
    "ecs:RunTask",
  ]
  resources = [
    "arn:aws:ecs:*:*:service/${aws_ecs_cluster.main.name}/*",
    "arn:aws:ecs:*:*:task/${aws_ecs_cluster.main.name}/*",
    "arn:aws:ecs:*:*:task-definition/switchboard-*",
  ]
}
```
Note: `ecs:RegisterTaskDefinition` and `ecs:DeregisterTaskDefinition` are account-level actions that require `resources = ["*"]` per AWS IAM docs. Those two must be separated into their own statement with `"*"`.

---

### CR-02: `:latest` Image Tag Conflicts with Immutable ECR Repositories

**File:** `infra/modules/ecs/services.tf:28` (and lines 113, 197, 258, 328)
**Issue:** Every task definition uses `image = "${var.ecr_repository_urls["..."]}:latest"`. The ECR module sets `image_tag_mutability = "IMMUTABLE"` (ecr/main.tf:14). Immutable ECR repositories reject any attempt to push an image with a tag that already exists. This means the first `docker push .../gateway:latest` succeeds, but every subsequent CI push will fail with `ImageAlreadyExistsException`. The ECR lifecycle policy also deletes images based on count, which could delete the only `:latest` image that the running task definition references, causing new task launches to fail.

**Fix:** Either (a) change ECR to `MUTABLE` for `:latest` and accept the tradeoff, or (b) use a specific tag (e.g. git commit SHA) in task definitions and update the tag on each deployment. Option (b) is the recommended practice:

```hcl
# Add to ecs/variables.tf
variable "image_tags" {
  type        = map(string)
  default     = { gateway = "latest", admin-api = "latest", echo = "latest", ping = "latest" }
  description = "Map of image name to tag to deploy. Override with git SHA in CI."
}

# In services.tf, replace hardcoded :latest:
image = "${var.ecr_repository_urls["gateway"]}:${var.image_tags["gateway"]}"
```

If `:latest` must be kept as a temporary bootstrap convenience, change `image_tag_mutability = "MUTABLE"` in ecr/main.tf and document the intent clearly.

---

## Warnings

### WR-01: ALB Security Group Ingress Allows 0.0.0.0/0 Instead of VPC CIDR

**File:** `infra/modules/alb/main.tf:30`
**Issue:** The ALB ingress rule for HTTPS uses `cidr_ipv4 = "0.0.0.0/0"`. The comment says "Direct Connect clients within the VPC" but the security group rule itself does not enforce this. While the ALB is `internal = true` (inaccessible from the public internet at the network level), the security group provides no VPC-level defence-in-depth. If the ALB type is ever inadvertently changed to external, or if the VPC is connected to an unintended network, the security group will not block traffic from non-VPC sources. The stated design intent (D-05: no internet-facing resources) should be enforced at both layers.

**Fix:**
```hcl
resource "aws_vpc_security_group_ingress_rule" "alb_https" {
  security_group_id = aws_security_group.alb.id
  description       = "HTTPS from Direct Connect clients within the VPC"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
  cidr_ipv4         = var.vpc_cidr_block  # Restrict to VPC CIDR, not 0.0.0.0/0
}
```

---

### WR-02: servicediscovery:DiscoverInstances Resource Scoping Is Silently Ineffective

**File:** `infra/modules/ecs/iam.tf:111-117`
**Issue:** The `CloudMapRead` policy statement scopes `servicediscovery:DiscoverInstances` to `[var.cloudmap_namespace_arn]`. However, `servicediscovery:DiscoverInstances` is an account-level action — AWS IAM does not support resource-level permissions for it (it requires `resources = ["*"]` in the IAM policy). The current policy will cause an IAM validation error or will effectively apply to `*` depending on how AWS evaluates it, but the intended namespace scoping is silently not enforced. The `GetNamespace` and `ListServices` actions are also not namespace-level resources in the IAM resource hierarchy; they require `*` or account-level ARNs.

**Fix:**
```hcl
data "aws_iam_policy_document" "gateway_task" {
  statement {
    sid = "CloudMapRead"
    actions = [
      "servicediscovery:DiscoverInstances",
    ]
    # DiscoverInstances does not support resource-scoping per AWS IAM docs
    resources = ["*"]
  }

  statement {
    sid = "CloudMapNamespaceRead"
    actions = [
      "servicediscovery:GetNamespace",
      "servicediscovery:ListServices",
    ]
    resources = [var.cloudmap_namespace_arn]
  }
  # ... rest of policy
}
```

---

### WR-03: Stale Server Object Returned After ECS Status Update

**File:** `switchboard/container/manager.py:188` (also lines 210, 232)
**Issue:** After updating server status via `repo.update_status()`, the methods call `session.get(type(server), server.id)` to return a refreshed instance. In an async SQLAlchemy session, `session.get()` checks the session's identity map first; if the entity was loaded in a different session context (which is the typical pattern in FastAPI with per-request sessions), `session.get()` may return a cached version that still shows the *old* status from before the update, or it may issue a SELECT that returns the updated row depending on isolation level. When `session.get()` returns `None` (entity not in identity map and the row was deleted, or the session is expired), the code returns the original `server` argument, which has the status from before the operation. Callers will receive a server object with incorrect status.

**Fix:** After the repository update, expire the entity and rely on the repository's return value rather than `session.get()`:

```python
async def _start_ecs(
    self,
    session: AsyncSession,
    server: Server,
    repo: ServerRepository,
) -> Server:
    """Start server via ECS service update (D-10: desiredCount=1)."""
    service_name = f"{CONTAINER_NAME_PREFIX}{server.name}"
    adapter = self._get_ecs_adapter()
    try:
        await adapter.start_service(service_name)
    except ContainerStartError:
        await repo.update_status(session, server.id, ServerStatus.error)
        raise
    updated = await repo.update_status(session, server.id, ServerStatus.running)
    return updated if updated is not None else server
```

This requires `repo.update_status()` to return the updated `Server` instance (it should if it uses `RETURNING` or a subsequent `SELECT`). Alternatively, call `await session.refresh(server)` after the update if the session still holds the identity.

---

### WR-04: StreamingResponse Forwards Hop-by-Hop Headers from Backend

**File:** `switchboard/gateway/proxy.py:157`
**Issue:** `dict(rp_resp.headers)` includes all backend response headers before they are forwarded to the client, including hop-by-hop headers such as `Transfer-Encoding`, `Connection`, `Keep-Alive`, and `Upgrade`. Forwarding these through an ASGI layer (Uvicorn/FastAPI/Starlette) can cause content decoding errors (e.g., the client expects `chunked` transfer encoding but Starlette's `StreamingResponse` already handles chunking), incorrect `Content-Length` (if the backend sent a compressed body that is decompressed by httpx), and connection management issues.

**Fix:**
```python
HOP_BY_HOP_HEADERS = frozenset({
    "connection", "keep-alive", "proxy-authenticate",
    "proxy-authorization", "te", "trailers",
    "transfer-encoding", "upgrade",
})

return StreamingResponse(
    rp_resp.aiter_raw(),
    status_code=rp_resp.status_code,
    headers={
        k: v
        for k, v in rp_resp.headers.items()
        if k.lower() not in HOP_BY_HOP_HEADERS
    },
    background=BackgroundTask(rp_resp.aclose),
)
```

---

### WR-05: Admin API Health Check Endpoint Is Unauthenticated and May Not Exist

**File:** `infra/modules/ecs/services.tf:141`
**Issue:** The admin API container health check calls `http://localhost:8000/api/v1/servers`. This endpoint likely requires authentication (it is a management endpoint). If the admin API enforces JWT validation on all routes, the health check will receive a 401 response, which is not in the `matcher` list for the health check. The ALB health check only checks the gateway target group (port 8000, path `/.well-known/oauth-protected-resource`), so this is an ECS container-level health check. If the health check always fails, ECS will restart the container in a loop. If the admin API has no unauthenticated health endpoint, the check should target a different path such as `/health` or `/`.

**Fix:** Add an unauthenticated health endpoint to the admin API and reference it here, or change the health check path to a known public path:

```hcl
healthCheck = {
  command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/health')\""]
  interval    = 10
  timeout     = 5
  retries     = 3
  startPeriod = 15
}
```

---

### WR-06: VPC Endpoints Security Group Has Unrestricted Egress

**File:** `infra/modules/vpc/main.tf:69-75`
**Issue:** The VPC endpoints security group allows all outbound traffic (`0.0.0.0/0`, all ports, all protocols). Interface VPC endpoints are passive — they accept inbound connections from services within the VPC and return responses; they do not initiate outbound connections to the internet. This egress rule adds no functional value and violates the principle of least privilege described in the project's threat model. An unrestricted egress on the VPC endpoint security group means any compromise of a service using that SG could egress to arbitrary internet addresses.

**Fix:**
```hcl
# Remove the permissive egress block entirely, or replace with:
egress {
  description = "HTTPS responses within VPC"
  from_port   = 443
  to_port     = 443
  protocol    = "tcp"
  cidr_blocks = [var.vpc_cidr]
}
```

---

## Info

### IN-01: acm_certificate_arn Commented Out in terraform.tfvars Will Cause Interactive Prompt

**File:** `infra/environments/dev/terraform.tfvars:5`
**Issue:** The `acm_certificate_arn` variable is required (no default in variables.tf) and is commented out in `terraform.tfvars`. Running `terraform plan` without setting it will trigger an interactive prompt, which breaks non-interactive CI pipelines.

**Fix:** Add a clear sentinel value with documentation, or ensure the variable is set via `TF_VAR_acm_certificate_arn` in CI:
```hcl
# acm_certificate_arn must be set before apply:
#   terraform apply -var="acm_certificate_arn=arn:aws:acm:..."
# Or export TF_VAR_acm_certificate_arn in CI pipeline.
acm_certificate_arn = ""  # PLACEHOLDER: set before apply
```
A `validation` block in variables.tf could also enforce a non-empty value with a helpful error message.

---

### IN-02: Secrets Created with recovery_window_in_days = 0 Allow Immediate Permanent Deletion

**File:** `infra/modules/secrets/main.tf:14` (also lines 23, 32)
**Issue:** All three secrets are created with `recovery_window_in_days = 0`, enabling force-deletion with no recovery window. In a shared dev environment, an accidental `terraform destroy` or a misfire of `aws secretsmanager delete-secret` will permanently destroy the JWT secrets and DATABASE_URL immediately. For dev this is a convenience tradeoff, but it is worth calling out explicitly as a deliberate choice.

**Fix:** For dev, this is acceptable. Consider setting `recovery_window_in_days = 7` or adding a lifecycle guard if the secrets are populated with real credentials:
```hcl
resource "aws_secretsmanager_secret" "database_url" {
  name                    = "switchboard/${var.environment}/DATABASE_URL"
  recovery_window_in_days = var.environment == "dev" ? 0 : 30
  # ...
}
```

---

### IN-03: get_settings Cache Not Cleaned Up in Finally Block in Test

**File:** `tests/gateway/test_proxy.py:115-144`
**Issue:** `test_resolve_backend_ecs_cloud_map_domain` clears `get_settings.cache_clear()` at the end of the test (line 144), but if the test body raises before reaching that line, the settings cache will remain with the `CLOUD_MAP_DOMAIN=.switchboard.local` value set, potentially affecting subsequent tests in the same process. The cleanup should be guaranteed regardless of test outcome.

**Fix:** Use a `try/finally` block, or move the setup/teardown to a pytest fixture:
```python
def test_resolve_backend_ecs_cloud_map_domain(
    monkeypatch: pytest.MonkeyPatch,
    customer_auth_headers,
) -> None:
    monkeypatch.setenv("CUSTOMER_JWT_SECRET", "pytest-customer-secret-32bytes!!")
    monkeypatch.setenv("OPERATOR_JWT_SECRET", "pytest-default-secret-32-bytes-min!")
    monkeypatch.setenv("CLOUD_MAP_DOMAIN", ".switchboard.local")
    from switchboard.config import get_settings
    get_settings.cache_clear()
    try:
        # ... test body ...
    finally:
        get_settings.cache_clear()
```

---

### IN-04: psycopg2-binary Listed as Dev Dependency

**File:** `pyproject.toml:27`
**Issue:** `psycopg2-binary` is listed as a dev dependency alongside `asyncpg`. The project uses `asyncpg` for all async database access. The `psycopg2-binary` inclusion suggests it may be needed for Alembic migrations or a script, but this is not documented. If it is used for synchronous migration runs, it should have a comment explaining why; if it is not needed, it adds unnecessary binary dependency overhead.

**Fix:** Add a comment if intentional, or remove if unused:
```toml
[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.26.0",
    "ruff>=0.11.0",
    # psycopg2-binary used by Alembic env.py for offline migrations
    "psycopg2-binary>=2.9.0",
    ...
]
```

---

### IN-05: ECS Container Health Check Python Command Will Pass on HTTP Error Responses

**File:** `infra/modules/ecs/services.tf:58-63` (and line 141)
**Issue:** The health check command uses `urllib.request.urlopen()` to verify container liveness. `urlopen` raises `urllib.error.HTTPError` for 4xx/5xx responses — but only when the response cannot be read, not on receipt. More precisely, `urlopen` will raise for HTTP errors by default, so a 500 will fail the health check. However, a 404 will also fail the health check (the endpoint must return 200). The ALB health check for the gateway explicitly uses `matcher = "200"`, which is consistent. The container-level health check does not have a matcher — it relies on `urlopen` raising or not. This is functionally correct but fragile; if the endpoint is protected by auth middleware that returns 401, `urlopen` will raise `HTTPError` and the health check will fail, cycling the container. Ensure the health check path is always unauthenticated.

**Fix:** Verify that `/.well-known/oauth-protected-resource` and `/api/v1/servers` are accessible without authentication from localhost, or switch to a dedicated `/health` endpoint. No code change required if the endpoints already return 200 without auth — this is a verification item.

---

_Reviewed: 2026-04-20_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
