# Outputs for the Switchboard dev environment.
#
# Surfaces key infrastructure identifiers needed for deployment
# workflows and operational access.

output "alb_dns_name" {
  value       = module.alb.alb_dns_name
  description = "DNS name of the internal ALB for Direct Connect routing."
}

output "ecs_cluster_arn" {
  value       = module.ecs.cluster_arn
  description = "ARN of the ECS cluster."
}

output "ecr_repository_urls" {
  value       = module.ecr.repository_urls
  description = "Map of image name to ECR repository URL for docker push targets."
}

output "rds_endpoint" {
  value       = module.rds.db_instance_endpoint
  description = "Connection endpoint for the RDS PostgreSQL instance (host:port)."
}

output "migration_task_definition_arn" {
  value       = module.ecs.migration_task_definition_arn
  description = "ARN for running Alembic migration via: aws ecs run-task --task-definition THIS_ARN"
}
