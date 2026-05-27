aws_region  = "us-east-1"
environment = "dev"
vpc_cidr    = "10.0.0.0/16"

# acm_certificate_arn = "arn:aws:acm:us-east-1:ACCOUNT_ID:certificate/CERT_ID"
# ^ Must be set before terraform apply. Request or import an ACM
#   certificate for the domain used by the internal ALB.
