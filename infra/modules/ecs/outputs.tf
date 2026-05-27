output "cluster_id" {
  value       = aws_ecs_cluster.main.id
  description = "ID of the ECS cluster."
}

output "cluster_arn" {
  value       = aws_ecs_cluster.main.arn
  description = "ARN of the ECS cluster."
}

output "cluster_name" {
  value       = aws_ecs_cluster.main.name
  description = "Name of the ECS cluster."
}

output "gateway_security_group_id" {
  value       = aws_security_group.gateway.id
  description = "Security group ID for the gateway ECS service."
}

output "admin_api_security_group_id" {
  value       = aws_security_group.admin_api.id
  description = "Security group ID for the admin API ECS service."
}

output "mcp_server_security_group_id" {
  value       = aws_security_group.mcp_server.id
  description = "Security group ID for MCP server ECS services. Ingress restricted to gateway only (D-08)."
}

output "migration_task_definition_arn" {
  value       = aws_ecs_task_definition.migration.arn
  description = "ARN of the Alembic migration task definition. Run via: aws ecs run-task --task-definition THIS_ARN"
}
