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
