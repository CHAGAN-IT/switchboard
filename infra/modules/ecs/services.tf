# ECS task definitions and services for Switchboard.
#
# Defines 5 task definitions (gateway, admin-api, echo, ping, migration)
# and 4 ECS services (gateway, admin-api, echo, ping). The migration
# task runs via `aws ecs run-task` post-deploy, not as a service (D-18).
#
# Secrets are injected via the `secrets` block with `valueFrom` ARN
# references -- never as plaintext environment variables (D-17, T-7-11).
#
# Echo and ping services register with Cloud Map for DNS-based
# service discovery (D-12).

# =============================================================================
# Gateway
# =============================================================================

resource "aws_ecs_task_definition" "gateway" {
  family                   = "switchboard-gateway"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.gateway_task.arn

  container_definitions = jsonencode([{
    name      = "gateway"
    image     = "${var.ecr_repository_urls["gateway"]}:${var.image_tags["gateway"]}"
    essential = true

    portMappings = [{
      containerPort = 8000
      protocol      = "tcp"
    }]

    secrets = [
      { name = "CUSTOMER_JWT_SECRET", valueFrom = var.customer_jwt_secret_arn },
      { name = "OPERATOR_JWT_SECRET", valueFrom = var.operator_jwt_secret_arn },
      { name = "DATABASE_URL", valueFrom = var.database_url_secret_arn },
    ]

    environment = [
      { name = "CLOUD_MAP_DOMAIN", value = ".switchboard.local" },
      { name = "AWS_REGION", value = var.aws_region },
      { name = "ECS_CLUSTER_ARN", value = aws_ecs_cluster.main.arn },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.gateway.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "gateway"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/.well-known/oauth-protected-resource')\""]
      interval    = 10
      timeout     = 5
      retries     = 3
      startPeriod = 15
    }
  }])

  tags = {
    Name        = "switchboard-gateway"
    Environment = var.environment
  }
}

resource "aws_ecs_service" "gateway" {
  name            = "switchboard-gateway"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.gateway.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = var.private_subnet_ids
    security_groups = [aws_security_group.gateway.id]
  }

  load_balancer {
    target_group_arn = var.gateway_target_group_arn
    container_name   = "gateway"
    container_port   = 8000
  }

  force_new_deployment = true

  tags = {
    Name        = "switchboard-gateway"
    Environment = var.environment
  }
}

# =============================================================================
# Admin API
# =============================================================================

resource "aws_ecs_task_definition" "admin_api" {
  family                   = "switchboard-admin-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.admin_api_task.arn

  container_definitions = jsonencode([{
    name      = "admin-api"
    image     = "${var.ecr_repository_urls["admin-api"]}:${var.image_tags["admin-api"]}"
    essential = true

    portMappings = [{
      containerPort = 8000
      protocol      = "tcp"
    }]

    secrets = [
      { name = "DATABASE_URL", valueFrom = var.database_url_secret_arn },
      { name = "OPERATOR_JWT_SECRET", valueFrom = var.operator_jwt_secret_arn },
    ]

    environment = [
      { name = "AWS_REGION", value = var.aws_region },
      { name = "ECS_CLUSTER_ARN", value = aws_ecs_cluster.main.arn },
      { name = "CLOUD_MAP_DOMAIN", value = ".switchboard.local" },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.admin_api.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "admin-api"
      }
    }

    healthCheck = {
      # /health is an unauthenticated endpoint -- /api/v1/servers requires
      # JWT auth and will return 401, cycling the container indefinitely.
      command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/health')\""]
      interval    = 10
      timeout     = 5
      retries     = 3
      startPeriod = 15
    }
  }])

  tags = {
    Name        = "switchboard-admin-api"
    Environment = var.environment
  }
}

# Admin API is internal-only -- NOT registered with ALB.
# Accessed within VPC by operators via Direct Connect.
resource "aws_ecs_service" "admin_api" {
  name            = "switchboard-admin-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.admin_api.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = var.private_subnet_ids
    security_groups = [aws_security_group.admin_api.id]
  }

  force_new_deployment = true

  tags = {
    Name        = "switchboard-admin-api"
    Environment = var.environment
  }
}

# =============================================================================
# Echo (Reference MCP Server)
# =============================================================================

resource "aws_ecs_task_definition" "echo" {
  family                   = "switchboard-echo"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.mcp_server_task.arn

  container_definitions = jsonencode([{
    name      = "echo"
    image     = "${var.ecr_repository_urls["echo"]}:${var.image_tags["echo"]}"
    essential = true

    portMappings = [{
      containerPort = 8000
      protocol      = "tcp"
    }]

    # No secrets needed -- reference servers do not access DB or JWT

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.echo.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "echo"
      }
    }
  }])

  tags = {
    Name        = "switchboard-echo"
    Environment = var.environment
  }
}

resource "aws_ecs_service" "echo" {
  name            = "switchboard-echo"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.echo.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = var.private_subnet_ids
    security_groups = [aws_security_group.mcp_server.id]
  }

  # Cloud Map registration for DNS-based service discovery (D-12)
  service_registries {
    registry_arn = var.cloudmap_service_arns["sb-echo"]
  }

  force_new_deployment = true

  tags = {
    Name        = "switchboard-echo"
    Environment = var.environment
  }
}

# =============================================================================
# Ping (Reference MCP Server)
# =============================================================================

resource "aws_ecs_task_definition" "ping" {
  family                   = "switchboard-ping"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.mcp_server_task.arn

  container_definitions = jsonencode([{
    name      = "ping"
    image     = "${var.ecr_repository_urls["ping"]}:${var.image_tags["ping"]}"
    essential = true

    portMappings = [{
      containerPort = 8000
      protocol      = "tcp"
    }]

    # No secrets needed -- reference servers do not access DB or JWT

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.ping.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "ping"
      }
    }
  }])

  tags = {
    Name        = "switchboard-ping"
    Environment = var.environment
  }
}

resource "aws_ecs_service" "ping" {
  name            = "switchboard-ping"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.ping.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = var.private_subnet_ids
    security_groups = [aws_security_group.mcp_server.id]
  }

  # Cloud Map registration for DNS-based service discovery (D-12)
  service_registries {
    registry_arn = var.cloudmap_service_arns["sb-ping"]
  }

  force_new_deployment = true

  tags = {
    Name        = "switchboard-ping"
    Environment = var.environment
  }
}

# =============================================================================
# Migration (Alembic) -- Run-task, NOT a service (D-18)
# =============================================================================
#
# The migration task reuses the admin-api image but overrides the
# command to run Alembic. It is executed via `aws ecs run-task`
# after deployment, not as a persistent service.

resource "aws_ecs_task_definition" "migration" {
  family                   = "switchboard-migration"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.mcp_server_task.arn

  container_definitions = jsonencode([{
    name      = "migration"
    image     = "${var.ecr_repository_urls["admin-api"]}:${var.image_tags["admin-api"]}"
    essential = true
    command   = ["uv", "run", "alembic", "upgrade", "head"]

    secrets = [
      { name = "DATABASE_URL", valueFrom = var.database_url_secret_arn },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.migration.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "migration"
      }
    }
  }])

  tags = {
    Name        = "switchboard-migration"
    Environment = var.environment
  }
}
