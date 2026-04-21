# ECS IAM roles for Switchboard.
#
# Four separate roles enforce least-privilege per D-15:
# 1. Execution role (shared): ECR pull, Secrets Manager read, CloudWatch write
# 2. Gateway task role: Cloud Map read, ECS describe
# 3. Admin API task role: ECS CRUD, ECR read, iam:PassRole (scoped)
# 4. MCP server task role: no AWS API permissions
#
# CRITICAL (T-7-10): No IAM policy uses Resource = "*". All are
# scoped to specific ARNs.

# --- Assume Role Policy ---
# Shared by all four roles -- allows ECS tasks to assume the role.

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# --- Execution Role ---
# Used by the ECS agent at task start to pull images from ECR,
# read secrets from Secrets Manager, and write logs to CloudWatch.

resource "aws_iam_role" "ecs_execution" {
  name               = "switchboard-ecs-execution-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json

  tags = {
    Name        = "switchboard-ecs-execution-${var.environment}"
    Environment = var.environment
  }
}

data "aws_iam_policy_document" "ecs_execution" {
  # ECR image pull permissions
  statement {
    sid = "ECRPull"
    actions = [
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = values(var.ecr_repository_arns)
  }

  # ECR auth token -- ecr:GetAuthorizationToken is an account-level
  # action that does not support resource-scoping per AWS IAM docs.
  # This is the sole exception to the "no Resource = *" rule (T-7-10).
  statement {
    sid       = "ECRAuth"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  # Secrets Manager read for injected secrets (T-7-11)
  statement {
    sid     = "SecretsRead"
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      var.database_url_secret_arn,
      var.operator_jwt_secret_arn,
      var.customer_jwt_secret_arn,
    ]
  }

  # CloudWatch Logs write
  statement {
    sid = "LogsWrite"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      "${aws_cloudwatch_log_group.gateway.arn}:*",
      "${aws_cloudwatch_log_group.admin_api.arn}:*",
      "${aws_cloudwatch_log_group.echo.arn}:*",
      "${aws_cloudwatch_log_group.ping.arn}:*",
      "${aws_cloudwatch_log_group.migration.arn}:*",
    ]
  }
}

resource "aws_iam_role_policy" "ecs_execution" {
  name   = "switchboard-ecs-execution-${var.environment}"
  role   = aws_iam_role.ecs_execution.id
  policy = data.aws_iam_policy_document.ecs_execution.json
}

# --- Gateway Task Role ---
# Runtime permissions for the gateway service: read Cloud Map for
# service discovery and describe ECS services/tasks for health info.

resource "aws_iam_role" "gateway_task" {
  name               = "switchboard-gateway-task-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json

  tags = {
    Name        = "switchboard-gateway-task-${var.environment}"
    Environment = var.environment
  }
}

data "aws_iam_policy_document" "gateway_task" {
  # Cloud Map service discovery: DiscoverInstances is an account-level action
  # that does not support resource-level permissions per AWS IAM docs.
  # This is a documented exception to the "no Resource = *" rule (T-7-10).
  statement {
    sid     = "CloudMapDiscover"
    actions = ["servicediscovery:DiscoverInstances"]
    resources = ["*"]
  }

  # GetNamespace and ListServices can be scoped to the namespace ARN.
  statement {
    sid = "CloudMapRead"
    actions = [
      "servicediscovery:GetNamespace",
      "servicediscovery:ListServices",
    ]
    resources = [var.cloudmap_namespace_arn]
  }

  # ECS describe for health/status queries.
  # Service ARNs are arn:aws:ecs:REGION:ACCOUNT:service/CLUSTER/SERVICE,
  # not arn:aws:ecs:REGION:ACCOUNT:cluster/CLUSTER/* (T-7-10).
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
}

resource "aws_iam_role_policy" "gateway_task" {
  name   = "switchboard-gateway-task-${var.environment}"
  role   = aws_iam_role.gateway_task.id
  policy = data.aws_iam_policy_document.gateway_task.json
}

# --- Admin API Task Role ---
# Runtime permissions for the admin API: ECS service CRUD for
# dynamic server management, ECR read for image listing, and
# iam:PassRole scoped to specific role ARNs (T-7-13).

resource "aws_iam_role" "admin_api_task" {
  name               = "switchboard-admin-api-task-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json

  tags = {
    Name        = "switchboard-admin-api-task-${var.environment}"
    Environment = var.environment
  }
}

data "aws_iam_policy_document" "admin_api_task" {
  # ECS service lifecycle management.
  # Service/task ARNs are arn:aws:ecs:REGION:ACCOUNT:service/CLUSTER/SERVICE
  # and arn:aws:ecs:REGION:ACCOUNT:task/CLUSTER/TASK-ID — not cluster-arn/*.
  # RegisterTaskDefinition and DeregisterTaskDefinition are account-level
  # actions that require resources = ["*"] per AWS IAM docs (T-7-10 exception).
  statement {
    sid = "ECSManageServices"
    actions = [
      "ecs:CreateService",
      "ecs:UpdateService",
      "ecs:DeleteService",
      "ecs:DescribeServices",
      "ecs:DescribeTasks",
      "ecs:RunTask",
    ]
    resources = [
      "arn:aws:ecs:*:*:service/${aws_ecs_cluster.main.name}/*",
      "arn:aws:ecs:*:*:task/${aws_ecs_cluster.main.name}/*",
      "arn:aws:ecs:*:*:task-definition/switchboard-*",
    ]
  }

  # RegisterTaskDefinition and DeregisterTaskDefinition do not support
  # resource-level permissions per AWS IAM docs -- account-level only.
  statement {
    sid = "ECSTaskDefinitions"
    actions = [
      "ecs:RegisterTaskDefinition",
      "ecs:DeregisterTaskDefinition",
    ]
    resources = ["*"]
  }

  # iam:PassRole scoped to execution and MCP server task roles only (T-7-13)
  statement {
    sid     = "PassRole"
    actions = ["iam:PassRole"]
    resources = [
      aws_iam_role.ecs_execution.arn,
      aws_iam_role.mcp_server_task.arn,
    ]
  }

  # ECR read for image listing
  statement {
    sid = "ECRRead"
    actions = [
      "ecr:DescribeRepositories",
      "ecr:ListImages",
    ]
    resources = values(var.ecr_repository_arns)
  }
}

resource "aws_iam_role_policy" "admin_api_task" {
  name   = "switchboard-admin-api-task-${var.environment}"
  role   = aws_iam_role.admin_api_task.id
  policy = data.aws_iam_policy_document.admin_api_task.json
}

# --- MCP Server Task Role ---
# Minimal role for reference servers (echo, ping). MCP servers
# need no AWS API permissions -- they only respond to proxied
# requests from the gateway. Also used by the migration task.

resource "aws_iam_role" "mcp_server_task" {
  name               = "switchboard-mcp-server-task-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json

  tags = {
    Name        = "switchboard-mcp-server-task-${var.environment}"
    Environment = var.environment
  }
}

# No policy attachment -- MCP servers need no AWS API permissions (D-15).
