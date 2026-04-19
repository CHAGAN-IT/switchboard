# Root Terraform configuration for Switchboard dev environment.
#
# Composes all shared modules into a working infrastructure stack.
# Cross-module dependencies are wired explicitly through outputs
# and variables (D-04).

# --- VPC ---

module "vpc" {
  source      = "../../modules/vpc"
  environment = var.environment
  aws_region  = var.aws_region
  vpc_cidr    = var.vpc_cidr
}

# --- ECR ---

module "ecr" {
  source      = "../../modules/ecr"
  environment = var.environment
}

# --- Secrets Manager ---

module "secrets" {
  source      = "../../modules/secrets"
  environment = var.environment
}

# --- RDS ---

module "rds" {
  source                     = "../../modules/rds"
  environment                = var.environment
  vpc_id                     = module.vpc.vpc_id
  private_subnet_ids         = module.vpc.private_subnet_ids
  allowed_security_group_ids = [module.ecs.gateway_security_group_id, module.ecs.admin_api_security_group_id]
}

# --- ALB ---

module "alb" {
  source              = "../../modules/alb"
  environment         = var.environment
  vpc_id              = module.vpc.vpc_id
  private_subnet_ids  = module.vpc.private_subnet_ids
  acm_certificate_arn = var.acm_certificate_arn
  vpc_cidr_block      = module.vpc.vpc_cidr_block
}

# --- Cloud Map ---

module "cloudmap" {
  source = "../../modules/cloudmap"
  vpc_id = module.vpc.vpc_id
}

# --- ECS ---

module "ecs" {
  source                  = "../../modules/ecs"
  environment             = var.environment
  vpc_id                  = module.vpc.vpc_id
  vpc_cidr_block          = module.vpc.vpc_cidr_block
  alb_security_group_id   = module.alb.alb_security_group_id
  private_subnet_ids      = module.vpc.private_subnet_ids
  aws_region              = var.aws_region
  ecr_repository_urls     = module.ecr.repository_urls
  ecr_repository_arns     = module.ecr.repository_arns
  database_url_secret_arn = module.secrets.database_url_secret_arn
  operator_jwt_secret_arn = module.secrets.operator_jwt_secret_arn
  customer_jwt_secret_arn = module.secrets.customer_jwt_secret_arn
  gateway_target_group_arn = module.alb.gateway_target_group_arn
  cloudmap_service_arns   = module.cloudmap.service_arns
  cloudmap_namespace_arn  = module.cloudmap.namespace_arn
  rds_security_group_id   = module.rds.db_security_group_id
}
