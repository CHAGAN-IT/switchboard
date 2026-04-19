variable "environment" {
  type        = string
  description = "Environment name (e.g. dev, prod). Used for resource naming."
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "IDs of private subnets for the RDS subnet group. Must span at least 2 AZs."
}

variable "vpc_id" {
  type        = string
  description = "ID of the VPC where the RDS instance is deployed."
}

variable "allowed_security_group_ids" {
  type        = list(string)
  description = "Security groups allowed to connect to RDS on port 5432."
}

variable "instance_class" {
  type        = string
  default     = "db.t3.micro"
  description = "RDS instance class. Use db.t3.micro for dev, scale up for prod."
}

variable "engine_version" {
  type        = string
  default     = "16"
  description = "PostgreSQL engine major version."
}
