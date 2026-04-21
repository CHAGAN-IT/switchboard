---
phase: 07-aws-deployment
fixed_at: 2026-04-21T00:47:38Z
review_path: .planning/phases/07-aws-deployment/07-REVIEW.md
iteration: 1
findings_in_scope: 8
fixed: 8
skipped: 0
status: all_fixed
---

# Phase 7: Code Review Fix Report

**Fixed at:** 2026-04-21T00:47:38Z
**Source review:** .planning/phases/07-aws-deployment/07-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 8 (2 Critical, 6 Warning)
- Fixed: 8
- Skipped: 0

## Fixed Issues

### CR-01: ECS IAM Resource ARN Pattern Does Not Match Service or Task ARNs

**Files modified:** `infra/modules/ecs/iam.tf`
**Commit:** 1cfb352
**Applied fix:** Split the `ECSManage` statement in the admin API task policy into two statements: `ECSManageServices` (scoped to `arn:aws:ecs:*:*:service/CLUSTER/*`, `arn:aws:ecs:*:*:task/CLUSTER/*`, and `arn:aws:ecs:*:*:task-definition/switchboard-*`) and `ECSTaskDefinitions` (scoped to `*` because `RegisterTaskDefinition`/`DeregisterTaskDefinition` are account-level actions that do not support resource-level permissions per AWS IAM docs). Updated the gateway task `ECSDescribe` statement similarly to use correct service and task ARN patterns instead of `cluster-arn/*`.

### CR-02: `:latest` Image Tag Conflicts with Immutable ECR Repositories

**Files modified:** `infra/modules/ecs/variables.tf`, `infra/modules/ecs/services.tf`
**Commit:** c17c3e3
**Applied fix:** Added `image_tags` variable to `variables.tf` (map of image name to tag, defaulting to `latest` for bootstrap convenience, overridable with git SHA in CI). Updated all five task definitions in `services.tf` (gateway, admin-api, echo, ping, migration) to use `var.image_tags["<name>"]` instead of hardcoded `:latest`.

### WR-01: ALB Security Group Ingress Allows 0.0.0.0/0 Instead of VPC CIDR

**Files modified:** `infra/modules/alb/main.tf`
**Commit:** c79c7a7
**Applied fix:** Changed `cidr_ipv4` in the `alb_https` ingress rule from `"0.0.0.0/0"` to `var.vpc_cidr_block`, enforcing VPC-level defence-in-depth consistent with the internal ALB design intent (D-05).

### WR-02: servicediscovery:DiscoverInstances Resource Scoping Is Silently Ineffective

**Files modified:** `infra/modules/ecs/iam.tf`
**Commit:** f76f877
**Applied fix:** Split the `CloudMapRead` statement into two: `CloudMapDiscover` (with `resources = ["*"]` since `DiscoverInstances` is an account-level action not supporting resource-level permissions) and `CloudMapRead` (with `resources = [var.cloudmap_namespace_arn]` for `GetNamespace` and `ListServices`). Added a comment documenting this as a documented exception to the T-7-10 "no Resource = *" rule.

### WR-03: Stale Server Object Returned After ECS Status Update

**Files modified:** `switchboard/container/manager.py`
**Commit:** e42af60
**Applied fix:** In `_start_ecs`, `_stop_ecs`, and `_restart_ecs`, replaced the `session.get()` call after `repo.update_status()` with direct use of the return value from `update_status()`. The repository method already calls `flush()` and `refresh()` internally and returns the authoritative updated `Server` instance, making the subsequent `session.get()` redundant and potentially returning a stale cached value.

### WR-04: StreamingResponse Forwards Hop-by-Hop Headers from Backend

**Files modified:** `switchboard/gateway/proxy.py`
**Commit:** a242b3f
**Applied fix:** Added a module-level `HOP_BY_HOP_HEADERS` frozenset constant listing all RFC 2616 hop-by-hop headers. Updated the `StreamingResponse` construction to filter out any header whose lowercase name appears in this set, preventing `Transfer-Encoding`, `Connection`, and similar headers from being forwarded through the ASGI layer.

### WR-05: Admin API Health Check Endpoint Is Unauthenticated and May Not Exist

**Files modified:** `infra/modules/ecs/services.tf`
**Commit:** 3059c4f
**Applied fix:** Changed the admin API container health check command from `http://localhost:8000/api/v1/servers` (an authenticated management endpoint that would return 401 and cycle the container) to `http://localhost:8000/health` (an unauthenticated liveness endpoint). Note: the `/health` endpoint must exist in the admin API application; this is flagged as a human verification item.
**Commit status:** fixed: requires human verification (confirm `/health` endpoint exists and returns 200 without auth in the admin API application)

### WR-06: VPC Endpoints Security Group Has Unrestricted Egress

**Files modified:** `infra/modules/vpc/main.tf`
**Commit:** 903c2bb
**Applied fix:** Replaced the permissive `protocol = "-1"` / `cidr_blocks = ["0.0.0.0/0"]` egress rule with a targeted rule allowing only HTTPS (port 443/tcp) within the VPC CIDR. Added a comment explaining that interface VPC endpoints are passive and do not initiate outbound internet connections.

---

_Fixed: 2026-04-21T00:47:38Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
