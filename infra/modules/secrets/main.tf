# Secrets Manager module for Switchboard.
#
# Creates placeholder secrets only -- no aws_secretsmanager_secret_version
# resources. Actual values are populated out of band via AWS CLI to
# keep secret values out of Terraform state (D-20, T-7-05, Pitfall 4).
#
# Populate after provisioning:
#   aws secretsmanager put-secret-value \
#     --secret-id switchboard/<env>/DATABASE_URL \
#     --secret-string "postgresql+asyncpg://..."

resource "aws_secretsmanager_secret" "database_url" {
  name                    = "switchboard/${var.environment}/DATABASE_URL"
  recovery_window_in_days = 0

  tags = {
    Name        = "switchboard-database-url-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_secretsmanager_secret" "operator_jwt_secret" {
  name                    = "switchboard/${var.environment}/OPERATOR_JWT_SECRET"
  recovery_window_in_days = 0

  tags = {
    Name        = "switchboard-operator-jwt-secret-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_secretsmanager_secret" "customer_jwt_secret" {
  name                    = "switchboard/${var.environment}/CUSTOMER_JWT_SECRET"
  recovery_window_in_days = 0

  tags = {
    Name        = "switchboard-customer-jwt-secret-${var.environment}"
    Environment = var.environment
  }
}
