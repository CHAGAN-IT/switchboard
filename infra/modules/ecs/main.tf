# ECS module for Switchboard.
#
# Creates a Fargate-only ECS cluster and three security groups that
# enforce network isolation between platform components (D-08, D-13).
#
# Critical security control (T-7-06): MCP server containers accept
# ingress ONLY from the gateway security group on port 8000. No
# direct access from ALB, VPC CIDR, or internet is permitted.

# --- ECS Cluster ---

resource "aws_ecs_cluster" "main" {
  name = "switchboard-${var.environment}"

  tags = {
    Name        = "switchboard-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name = aws_ecs_cluster.main.name

  capacity_providers = ["FARGATE"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
  }
}

# --- Gateway Security Group ---
#
# The gateway sits between the ALB and MCP servers. It accepts
# traffic from the ALB and forwards proxied requests to MCP
# server containers.

resource "aws_security_group" "gateway" {
  name        = "switchboard-gateway-${var.environment}"
  description = "Gateway ECS service: accepts from ALB, forwards to MCP servers"
  vpc_id      = var.vpc_id

  tags = {
    Name        = "switchboard-gateway-${var.environment}"
    Environment = var.environment
  }
}

# Ingress: ALB -> gateway on port 8000
resource "aws_vpc_security_group_ingress_rule" "gateway_from_alb" {
  security_group_id            = aws_security_group.gateway.id
  description                  = "HTTP from ALB to gateway"
  from_port                    = 8000
  to_port                      = 8000
  ip_protocol                  = "tcp"
  referenced_security_group_id = var.alb_security_group_id
}

# Egress: gateway -> MCP servers on port 8000
resource "aws_vpc_security_group_egress_rule" "gateway_to_mcp" {
  security_group_id            = aws_security_group.gateway.id
  description                  = "Forward proxied requests to MCP server containers"
  from_port                    = 8000
  to_port                      = 8000
  ip_protocol                  = "tcp"
  referenced_security_group_id = aws_security_group.mcp_server.id
}

# Egress: gateway -> VPC CIDR on port 443 (AWS API calls via VPC endpoints)
resource "aws_vpc_security_group_egress_rule" "gateway_to_aws_apis" {
  security_group_id = aws_security_group.gateway.id
  description       = "HTTPS to VPC endpoints (Cloud Map, ECS describe)"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
  cidr_ipv4         = var.vpc_cidr_block
}

# Egress: gateway -> VPC CIDR on port 5432 (database access)
resource "aws_vpc_security_group_egress_rule" "gateway_to_db" {
  security_group_id = aws_security_group.gateway.id
  description       = "PostgreSQL to RDS (narrowed by RDS security group)"
  from_port         = 5432
  to_port           = 5432
  ip_protocol       = "tcp"
  cidr_ipv4         = var.vpc_cidr_block
}

# --- Admin API Security Group ---
#
# The admin API manages server registration and lifecycle. It
# needs access to ECS APIs (via VPC endpoints) and the database.

resource "aws_security_group" "admin_api" {
  name        = "switchboard-admin-api-${var.environment}"
  description = "Admin API ECS service: internal access for server management"
  vpc_id      = var.vpc_id

  tags = {
    Name        = "switchboard-admin-api-${var.environment}"
    Environment = var.environment
  }
}

# Ingress: ALB -> admin API on port 8000
resource "aws_vpc_security_group_ingress_rule" "admin_from_alb" {
  security_group_id            = aws_security_group.admin_api.id
  description                  = "HTTP from ALB to admin API"
  from_port                    = 8000
  to_port                      = 8000
  ip_protocol                  = "tcp"
  referenced_security_group_id = var.alb_security_group_id
}

# Egress: admin API -> VPC CIDR on port 443 (AWS API calls via VPC endpoints)
resource "aws_vpc_security_group_egress_rule" "admin_to_aws_apis" {
  security_group_id = aws_security_group.admin_api.id
  description       = "HTTPS to VPC endpoints (ECS create/update/delete, ECR pull)"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
  cidr_ipv4         = var.vpc_cidr_block
}

# Egress: admin API -> VPC CIDR on port 5432 (database access)
resource "aws_vpc_security_group_egress_rule" "admin_to_db" {
  security_group_id = aws_security_group.admin_api.id
  description       = "PostgreSQL to RDS (narrowed by RDS security group)"
  from_port         = 5432
  to_port           = 5432
  ip_protocol       = "tcp"
  cidr_ipv4         = var.vpc_cidr_block
}

# --- MCP Server Security Group ---
#
# CRITICAL SECURITY CONTROL (D-08, T-7-06):
# MCP server containers accept ingress ONLY from the gateway
# security group. No other source can reach them. This prevents
# lateral movement and ensures all customer traffic flows through
# the authenticated gateway proxy.

resource "aws_security_group" "mcp_server" {
  name        = "switchboard-mcp-server-${var.environment}"
  description = "MCP server containers: ingress from gateway ONLY (D-08)"
  vpc_id      = var.vpc_id

  tags = {
    Name        = "switchboard-mcp-server-${var.environment}"
    Environment = var.environment
  }
}

# Ingress: gateway -> MCP server on port 8000 ONLY
# No other ingress rules exist -- this is the sole access path.
resource "aws_vpc_security_group_ingress_rule" "mcp_from_gateway" {
  security_group_id            = aws_security_group.mcp_server.id
  description                  = "HTTP from gateway proxy only (D-08 enforcement)"
  from_port                    = 8000
  to_port                      = 8000
  ip_protocol                  = "tcp"
  referenced_security_group_id = aws_security_group.gateway.id
}

# No egress rules for MCP servers -- they only respond to proxied
# requests and do not initiate outbound connections.
