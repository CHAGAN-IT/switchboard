variable "environment" {
  type        = string
  description = "Environment name (e.g. dev, prod). Used for resource naming and tagging."
}

variable "vpc_id" {
  type        = string
  description = "ID of the VPC where the ALB and target group are created."
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "IDs of the private subnets for ALB placement (at least 2 AZs required)."
}

variable "acm_certificate_arn" {
  type        = string
  description = "ARN of the ACM certificate for TLS termination on the HTTPS listener."
}

variable "vpc_cidr_block" {
  type        = string
  description = "VPC CIDR block for ALB egress rules (health checks and forwarding)."
}
