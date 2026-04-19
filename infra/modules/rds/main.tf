# RDS PostgreSQL module for Switchboard.
#
# Deploys a PostgreSQL 16 instance in private subnets with
# encrypted storage. Network access restricted to explicitly
# allowed security groups on port 5432 (T-7-03).
#
# Master password is managed by AWS via manage_master_user_password,
# which stores it automatically in Secrets Manager.

resource "aws_db_subnet_group" "main" {
  name       = "switchboard-${var.environment}"
  subnet_ids = var.private_subnet_ids

  tags = {
    Name = "switchboard-${var.environment}"
  }
}

resource "aws_security_group" "rds" {
  name        = "switchboard-rds-${var.environment}"
  description = "RDS PostgreSQL access restricted to allowed security groups"
  vpc_id      = var.vpc_id

  tags = {
    Name = "switchboard-rds-${var.environment}"
  }
}

resource "aws_security_group_rule" "rds_ingress" {
  count = length(var.allowed_security_group_ids)

  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.rds.id
  source_security_group_id = var.allowed_security_group_ids[count.index]
}

resource "aws_db_instance" "main" {
  identifier = "switchboard-${var.environment}"

  engine         = "postgres"
  engine_version = var.engine_version
  instance_class = var.instance_class

  allocated_storage = 20
  storage_encrypted = true

  db_name  = "switchboard"
  username = "switchboard"

  # AWS manages the master password in Secrets Manager automatically.
  # No plaintext password in Terraform state (T-7-02, T-7-05).
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  # Dev settings -- override for production
  skip_final_snapshot = true
  multi_az            = false

  tags = {
    Name = "switchboard-${var.environment}"
  }
}
