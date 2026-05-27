---
phase: 07-aws-deployment
plan: 02
subsystem: infra
tags: [terraform, alb, cloudmap, ecs, fargate, security-groups, service-discovery]

# Dependency graph
requires:
  - phase: 07-aws-deployment/01
    provides: VPC module with private subnets, CIDR block, and VPC endpoints
provides:
  - Internal ALB with TLS termination and gateway target group
  - Cloud Map private DNS namespace (switchboard.local) with MCP service entries
  - ECS Fargate cluster with three security groups (gateway, admin-api, mcp-server)
  - Network isolation enforcing gateway-only access to MCP servers (D-08)
affects: [07-aws-deployment/03, 07-aws-deployment/04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "aws_vpc_security_group_ingress/egress_rule resources (modern Terraform API) over inline ingress/egress blocks"
    - "Cloud Map TTL=10 with failure_threshold=1 for fast DNS deregistration"
    - "Security group chaining (ALB -> gateway -> MCP server) for least-privilege network isolation"

key-files:
  created:
    - infra/modules/alb/main.tf
    - infra/modules/alb/variables.tf
    - infra/modules/alb/outputs.tf
    - infra/modules/cloudmap/main.tf
    - infra/modules/cloudmap/variables.tf
    - infra/modules/cloudmap/outputs.tf
    - infra/modules/ecs/main.tf
    - infra/modules/ecs/variables.tf
    - infra/modules/ecs/outputs.tf
  modified: []

key-decisions:
  - "Used aws_vpc_security_group_ingress/egress_rule resources instead of inline blocks for better composability and independent lifecycle management"
  - "ALB egress restricted to port 8000 on VPC CIDR (not all ports) for least-privilege forwarding"
  - "Admin API gets its own security group separate from gateway for independent ingress/egress control"
  - "MCP server SG has zero egress rules since MCP servers only respond to proxied requests"

patterns-established:
  - "Security group chaining: ALB SG -> gateway SG -> MCP server SG with referenced_security_group_id"
  - "Cloud Map service entry per MCP server using for_each on service_names variable"
  - "acm_certificate_arn as required variable (no default) to enforce TLS configuration"

requirements-completed: [PLAT-02]

# Metrics
duration: 3min
completed: 2026-04-19
---

# Phase 7 Plan 2: Networking and Service Discovery Summary

**Internal ALB with TLS 1.3 termination, Cloud Map private DNS namespace (switchboard.local), and ECS Fargate cluster with security group chain enforcing gateway-only MCP server access (D-08)**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-19T18:07:53Z
- **Completed:** 2026-04-19T18:11:27Z
- **Tasks:** 2
- **Files created:** 9

## Accomplishments
- Internal ALB with HTTPS listener (TLS 1.3 policy) forwarding to gateway target group on port 8000
- Cloud Map private DNS namespace with service discovery entries for MCP servers (TTL=10, failure_threshold=1)
- ECS Fargate cluster with three security groups enforcing strict network isolation
- MCP server security group allows ingress ONLY from gateway SG -- no lateral movement possible (T-7-06)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create ALB and Cloud Map modules** - `1580a59` (feat)
2. **Task 2: Create ECS cluster module with security groups** - `3aa30ed` (feat)

## Files Created/Modified
- `infra/modules/alb/main.tf` - Internal ALB, security group, gateway target group, HTTPS listener with TLS 1.3
- `infra/modules/alb/variables.tf` - Environment, VPC, subnets, ACM certificate ARN (required)
- `infra/modules/alb/outputs.tf` - ALB ARN, DNS name, SG ID, target group ARN
- `infra/modules/cloudmap/main.tf` - Private DNS namespace and service discovery entries with for_each
- `infra/modules/cloudmap/variables.tf` - VPC ID, namespace name, service names list
- `infra/modules/cloudmap/outputs.tf` - Namespace ID, ARN, service ARNs map
- `infra/modules/ecs/main.tf` - ECS Fargate cluster, gateway/admin-api/mcp-server security groups
- `infra/modules/ecs/variables.tf` - Environment, VPC, ALB SG ID, VPC CIDR
- `infra/modules/ecs/outputs.tf` - Cluster ID/ARN/name, three security group IDs

## Decisions Made
- Used modern `aws_vpc_security_group_ingress_rule` and `aws_vpc_security_group_egress_rule` resources (not inline blocks) for better lifecycle management and composability between modules
- ALB egress limited to port 8000 within VPC CIDR rather than all ports -- follows least-privilege
- Admin API gets a separate security group from the gateway for independent access control
- MCP server security group has zero egress rules because MCP servers only respond to proxied requests and do not initiate outbound connections
- Added `vpc_cidr_block` variable to ALB module for scoped egress rules (plan mentioned "egress to all within VPC CIDR" -- variable makes this explicit)

## Deviations from Plan

None - plan executed exactly as written.

## Threat Mitigations Verified

| Threat ID | Mitigation | Verified |
|-----------|-----------|----------|
| T-7-06 | MCP server SG ingress from gateway SG only | Yes - single `aws_vpc_security_group_ingress_rule` with `referenced_security_group_id` |
| T-7-07 | TLS 1.3 on ALB listener | Yes - `ELBSecurityPolicy-TLS13-1-2-2021-06` |
| T-7-08 | Fast DNS deregistration | Yes - TTL=10, failure_threshold=1 |
| T-7-09 | ALB internal only | Yes - `internal = true`, accepted risk |

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- ALB, Cloud Map, and ECS modules ready for dev environment composition (Plan 03)
- Outputs expose all IDs needed by ECS service task definitions
- Security group IDs ready for cross-module references in the dev environment root module

## Self-Check: PASSED

All 9 created files verified on disk. Both task commits (1580a59, 3aa30ed) verified in git log.

---
*Phase: 07-aws-deployment*
*Completed: 2026-04-19*
