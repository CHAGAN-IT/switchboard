---
status: partial
phase: 07-aws-deployment
source: [07-VERIFICATION.md]
started: 2026-04-20T13:11:32Z
updated: 2026-04-20T13:11:32Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Full Stack Provisioning via terraform apply
expected: Run `terraform apply` in `infra/environments/dev/` with valid AWS credentials and an ACM certificate ARN. All 4 ECS services (gateway, admin-api, echo, ping) must reach RUNNING/HEALTHY state. Resources provision cleanly, ECS cluster shows 4 healthy services, RDS reaches `available` state.
result: [pending]

### 2. End-to-End HTTPS Request Routing
expected: From within the VPC, send a JWT-authenticated customer request to the ALB DNS name at `/servers/echo/mcp` and verify the echo MCP server responds through the gateway proxy. HTTP 200 from echo task, routed through ALB → gateway → Cloud Map DNS → echo container.
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
