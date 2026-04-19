variable "environment" {
  type        = string
  description = "Environment name (e.g. dev, prod). Used for resource tagging."
}

variable "image_names" {
  type        = list(string)
  default     = ["gateway", "admin-api", "echo", "ping"]
  description = "Names of container images to create ECR repositories for."
}
