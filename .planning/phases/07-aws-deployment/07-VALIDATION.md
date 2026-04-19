---
phase: 7
slug: aws-deployment
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-19
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 0.26.x |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `uv run pytest tests/ -x -q --ignore=tests/reference_servers` |
| **Full suite command** | `uv run pytest tests/ -q` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/container/ tests/gateway/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 7-infra-01 | infra | 1 | PLAT-02 | T-7-01 | terraform plan succeeds for dev | smoke | `cd infra/environments/dev && terraform plan` | ❌ W0 | ⬜ pending |
| 7-ecs-01 | ecs-adapter | 1 | PLAT-02 | T-7-02 | ECS adapter routes when ECS_CONTAINER_METADATA_URI set | unit | `uv run pytest tests/container/test_ecs_adapter.py -x` | ❌ W0 | ⬜ pending |
| 7-ecs-02 | ecs-adapter | 1 | PLAT-02 | T-7-02 | ECS adapter calls update_service(desiredCount=1) for start | unit | `uv run pytest tests/container/test_ecs_adapter.py::TestStart -x` | ❌ W0 | ⬜ pending |
| 7-ecs-03 | ecs-adapter | 1 | PLAT-02 | T-7-02 | ECS adapter calls update_service(desiredCount=0) for stop | unit | `uv run pytest tests/container/test_ecs_adapter.py::TestStop -x` | ❌ W0 | ⬜ pending |
| 7-ecs-04 | ecs-adapter | 1 | PLAT-02 | T-7-02 | ECS adapter calls update_service(forceNewDeployment=True) for restart | unit | `uv run pytest tests/container/test_ecs_adapter.py::TestRestart -x` | ❌ W0 | ⬜ pending |
| 7-ecs-05 | ecs-adapter | 1 | PLAT-02 | T-7-02 | _is_ecs_environment() returns True when env var set | unit | `uv run pytest tests/container/test_ecs_adapter.py::TestEnvDetection -x` | ❌ W0 | ⬜ pending |
| 7-cfg-01 | ecs-adapter | 1 | PLAT-02 | — | Settings class accepts aws_region, ecs_cluster_arn, cloud_map_domain | unit | `uv run pytest tests/test_config_ecs.py -x` | ❌ W0 | ⬜ pending |
| 7-gw-01 | ecs-adapter | 2 | PLAT-02 | T-7-03 | resolve_backend() appends Cloud Map domain when configured | unit | `uv run pytest tests/gateway/test_proxy.py -x` | Existing (needs update) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/container/test_ecs_adapter.py` — stubs for ECS adapter start/stop/restart/env detection (PLAT-02)
- [ ] `tests/test_config_ecs.py` — covers new Settings fields (aws_region, ecs_cluster_arn, cloud_map_domain)
- [ ] `tests/gateway/test_proxy.py` — update existing tests for Cloud Map domain suffix behavior
- [ ] `uv add boto3` — add boto3 as production dependency if not present

*Existing test infrastructure in pyproject.toml covers all other phase requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `cdk deploy` → all ECS services healthy | PLAT-02 | Requires live AWS account with credentials | Run `cd infra/environments/dev && terraform apply`, verify ECS services reach RUNNING state in console |
| MCP requests over HTTPS routed correctly | PLAT-02 | Requires live AWS environment with ACM cert | Send test MCP request to ALB DNS name, verify response from correct backend |
| MCP containers in private subnets only | PLAT-02 | Infrastructure topology — requires AWS console | Verify security group rules in console: MCP SG allows ingress only from gateway SG on port 8000 |
| Failed health check stops traffic | PLAT-02 | Requires live ECS fault injection | Stop health endpoint on a running task, verify ALB stops routing to it within health check grace period |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
