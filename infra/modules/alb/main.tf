# ALB module for Switchboard.
#
# Creates an internal Application Load Balancer with TLS termination
# for customer traffic (D-06). The ALB sits in private subnets and
# is accessible only via Direct Connect -- not internet-facing.
#
# TLS 1.3 policy mitigates unencrypted traffic risk (T-7-07).
# The gateway target group uses IP targeting as required by Fargate
# awsvpc networking mode.

# --- ALB Security Group ---

resource "aws_security_group" "alb" {
  name        = "switchboard-alb-${var.environment}"
  description = "Controls traffic to and from the internal ALB"
  vpc_id      = var.vpc_id

  tags = {
    Name        = "switchboard-alb-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_vpc_security_group_ingress_rule" "alb_https" {
  security_group_id = aws_security_group.alb.id
  description       = "HTTPS from Direct Connect clients within the VPC"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "alb_to_vpc" {
  security_group_id = aws_security_group.alb.id
  description       = "Forward traffic to gateway and perform health checks within VPC"
  from_port         = 8000
  to_port           = 8000
  ip_protocol       = "tcp"
  cidr_ipv4         = var.vpc_cidr_block
}

# --- Application Load Balancer ---

resource "aws_lb" "main" {
  name               = "switchboard-${var.environment}"
  internal           = true
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.private_subnet_ids

  tags = {
    Name        = "switchboard-${var.environment}"
    Environment = var.environment
  }
}

# --- Gateway Target Group ---

resource "aws_lb_target_group" "gateway" {
  name        = "sb-gateway-${var.environment}"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = "/.well-known/oauth-protected-resource"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
    matcher             = "200"
  }

  tags = {
    Name        = "sb-gateway-${var.environment}"
    Environment = var.environment
  }
}

# --- HTTPS Listener ---
#
# TLS 1.3 policy (ELBSecurityPolicy-TLS13-1-2-2021-06) enforces
# minimum TLS 1.2 with TLS 1.3 preferred, mitigating T-7-07.

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.acm_certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.gateway.arn
  }
}
