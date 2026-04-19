output "database_url_secret_arn" {
  value       = aws_secretsmanager_secret.database_url.arn
  description = "ARN of the DATABASE_URL secret placeholder."
}

output "operator_jwt_secret_arn" {
  value       = aws_secretsmanager_secret.operator_jwt_secret.arn
  description = "ARN of the OPERATOR_JWT_SECRET secret placeholder."
}

output "customer_jwt_secret_arn" {
  value       = aws_secretsmanager_secret.customer_jwt_secret.arn
  description = "ARN of the CUSTOMER_JWT_SECRET secret placeholder."
}
