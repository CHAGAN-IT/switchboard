output "alb_arn" {
  value       = aws_lb.main.arn
  description = "ARN of the internal Application Load Balancer."
}

output "alb_dns_name" {
  value       = aws_lb.main.dns_name
  description = "DNS name of the internal ALB for Direct Connect routing."
}

output "alb_security_group_id" {
  value       = aws_security_group.alb.id
  description = "Security group ID of the ALB, used by ECS module for ingress rules."
}

output "gateway_target_group_arn" {
  value       = aws_lb_target_group.gateway.arn
  description = "ARN of the gateway target group for ECS service registration."
}
