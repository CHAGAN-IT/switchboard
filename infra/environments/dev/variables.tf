# Input variables for the Switchboard dev environment.

variable "aws_region" {
  type        = string
  default     = "us-east-1"
  description = "AWS region for all resources."
}

variable "environment" {
  type        = string
  default     = "dev"
  description = "Environment name, used for resource naming and tagging."
}

variable "acm_certificate_arn" {
  type        = string
  description = "ARN of the ACM certificate for ALB TLS termination. Must be provided before terraform apply."
}

variable "vpc_cidr" {
  type        = string
  default     = "10.0.0.0/16"
  description = "CIDR block for the Switchboard VPC."
}
