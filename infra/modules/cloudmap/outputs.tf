output "namespace_id" {
  value       = aws_service_discovery_private_dns_namespace.main.id
  description = "ID of the private DNS namespace."
}

output "namespace_arn" {
  value       = aws_service_discovery_private_dns_namespace.main.arn
  description = "ARN of the private DNS namespace."
}

output "service_arns" {
  value       = { for k, v in aws_service_discovery_service.mcp : k => v.arn }
  description = "Map of service name to Cloud Map service ARN for ECS service registration."
}
