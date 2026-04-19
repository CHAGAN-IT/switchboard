# CloudWatch log groups for Switchboard ECS services.
#
# Each service writes to a dedicated log group with a 30-day
# retention policy. Log groups are created by Terraform (not by
# the ECS agent) to ensure consistent naming and retention.

resource "aws_cloudwatch_log_group" "gateway" {
  name              = "/switchboard/${var.environment}/gateway"
  retention_in_days = 30

  tags = {
    Name        = "switchboard-gateway-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_cloudwatch_log_group" "admin_api" {
  name              = "/switchboard/${var.environment}/admin-api"
  retention_in_days = 30

  tags = {
    Name        = "switchboard-admin-api-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_cloudwatch_log_group" "echo" {
  name              = "/switchboard/${var.environment}/echo"
  retention_in_days = 30

  tags = {
    Name        = "switchboard-echo-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_cloudwatch_log_group" "ping" {
  name              = "/switchboard/${var.environment}/ping"
  retention_in_days = 30

  tags = {
    Name        = "switchboard-ping-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_cloudwatch_log_group" "migration" {
  name              = "/switchboard/${var.environment}/migration"
  retention_in_days = 30

  tags = {
    Name        = "switchboard-migration-${var.environment}"
    Environment = var.environment
  }
}
