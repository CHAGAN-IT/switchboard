output "repository_urls" {
  value       = { for k, v in aws_ecr_repository.main : k => v.repository_url }
  description = "Map of image name to ECR repository URL."
}

output "repository_arns" {
  value       = { for k, v in aws_ecr_repository.main : k => v.arn }
  description = "Map of image name to ECR repository ARN."
}
