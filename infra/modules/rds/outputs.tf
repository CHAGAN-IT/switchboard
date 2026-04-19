output "db_instance_endpoint" {
  value       = aws_db_instance.main.endpoint
  description = "Connection endpoint for the RDS instance (host:port)."
}

output "db_instance_arn" {
  value       = aws_db_instance.main.arn
  description = "ARN of the RDS instance."
}

output "db_security_group_id" {
  value       = aws_security_group.rds.id
  description = "Security group ID for the RDS instance. Use to grant ingress from other services."
}

output "db_master_secret_arn" {
  value       = aws_db_instance.main.master_user_secret[0].secret_arn
  description = "ARN of the auto-managed RDS master password secret in Secrets Manager."
}
