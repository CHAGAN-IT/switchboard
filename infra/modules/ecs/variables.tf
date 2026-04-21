variable "environment" {
  type        = string
  description = "Environment name (e.g. dev, prod). Used for resource naming and tagging."
}

variable "vpc_id" {
  type        = string
  description = "ID of the VPC where security groups are created."
}

variable "alb_security_group_id" {
  type        = string
  description = "Security group ID of the ALB, used for gateway ingress rules."
}

variable "vpc_cidr_block" {
  type        = string
  description = "VPC CIDR block for egress rules (AWS API calls, database access)."
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "IDs of the private subnets for ECS service network configuration."
}

variable "aws_region" {
  type        = string
  description = "AWS region for log group and environment configuration."
}

variable "ecr_repository_urls" {
  type        = map(string)
  description = "Map of image name to ECR repository URL (e.g. gateway => 123456.dkr.ecr.us-east-1.amazonaws.com/switchboard-gateway-dev)."
}

variable "ecr_repository_arns" {
  type        = map(string)
  description = "Map of image name to ECR repository ARN for IAM policy scoping."
}

variable "database_url_secret_arn" {
  type        = string
  description = "ARN of the DATABASE_URL secret in Secrets Manager."
}

variable "operator_jwt_secret_arn" {
  type        = string
  description = "ARN of the OPERATOR_JWT_SECRET secret in Secrets Manager."
}

variable "customer_jwt_secret_arn" {
  type        = string
  description = "ARN of the CUSTOMER_JWT_SECRET secret in Secrets Manager."
}

variable "gateway_target_group_arn" {
  type        = string
  description = "ARN of the ALB target group for the gateway ECS service."
}

variable "cloudmap_service_arns" {
  type        = map(string)
  description = "Map of service name to Cloud Map service ARN for ECS service registration."
}

variable "cloudmap_namespace_arn" {
  type        = string
  description = "ARN of the Cloud Map private DNS namespace."
}

variable "rds_security_group_id" {
  type        = string
  description = "Security group ID of the RDS instance, for reference in network rules."
}

variable "image_tags" {
  type        = map(string)
  description = "Map of image name to tag to deploy. Override with git SHA in CI to avoid collisions with immutable ECR repositories."
  default     = { gateway = "latest", admin-api = "latest", echo = "latest", ping = "latest" }
}
