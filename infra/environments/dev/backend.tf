# Terraform backend and provider configuration for Switchboard dev.
#
# Uses S3 native locking (use_lockfile = true) instead of DynamoDB,
# which is the current standard as of Terraform 1.11+ (D-02).

terraform {
  required_version = "~> 1.14"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  backend "s3" {
    bucket       = "switchboard-terraform-state"
    key          = "dev/terraform.tfstate"
    region       = "us-east-1"
    use_lockfile = true
    encrypt      = true
  }
}

provider "aws" {
  region = var.aws_region
}
