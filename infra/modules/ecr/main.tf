# ECR module for Switchboard.
#
# Creates one repository per container image. Tags are immutable
# to prevent tampering (T-7-04). Scan on push catches known
# vulnerabilities before deployment.
#
# Image builds and pushes are handled by CI/CD (future phase).
# Terraform plan succeeds even with empty repositories (D-22).

resource "aws_ecr_repository" "main" {
  for_each = toset(var.image_names)

  name                 = "switchboard/${each.value}"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name        = "switchboard-${each.value}"
    Environment = var.environment
  }
}

resource "aws_ecr_lifecycle_policy" "main" {
  for_each = toset(var.image_names)

  repository = aws_ecr_repository.main[each.key].name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}
