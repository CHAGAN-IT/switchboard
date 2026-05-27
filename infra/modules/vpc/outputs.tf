output "vpc_id" {
  value       = aws_vpc.main.id
  description = "ID of the Switchboard VPC."
}

output "private_subnet_ids" {
  value       = aws_subnet.private[*].id
  description = "IDs of the private subnets across availability zones."
}

output "vpc_cidr_block" {
  value       = aws_vpc.main.cidr_block
  description = "CIDR block of the VPC."
}

output "vpc_endpoints_security_group_id" {
  value       = aws_security_group.vpc_endpoints.id
  description = "Security group ID attached to VPC interface endpoints."
}
