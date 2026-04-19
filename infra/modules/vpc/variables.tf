variable "vpc_cidr" {
  type        = string
  default     = "10.0.0.0/16"
  description = "CIDR block for the Switchboard VPC."
}

variable "environment" {
  type        = string
  description = "Environment name (e.g. dev, prod). Used for resource naming and tagging."
}

variable "aws_region" {
  type        = string
  description = "AWS region. Used to construct VPC endpoint service names."
}
