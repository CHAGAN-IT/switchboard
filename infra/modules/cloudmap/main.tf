# Cloud Map module for Switchboard.
#
# Creates a private DNS namespace and service discovery entries so
# the gateway can resolve MCP server containers by hostname (D-07,
# D-12). Pattern: http://sb-{name}.switchboard.local:8000
#
# TTL=10 and failure_threshold=1 ensure fast deregistration of
# unhealthy instances, mitigating stale DNS records (T-7-08,
# Pitfall 3 from research).

# --- Private DNS Namespace ---

resource "aws_service_discovery_private_dns_namespace" "main" {
  name        = var.namespace_name
  vpc         = var.vpc_id
  description = "Switchboard MCP server discovery"
}

# --- Service Discovery Entries ---
#
# One entry per MCP server. ECS services register their task IPs
# here automatically when `service_registries` is configured on
# the ECS service definition.

resource "aws_service_discovery_service" "mcp" {
  for_each = toset(var.service_names)

  name = each.value

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.main.id

    dns_records {
      ttl  = 10
      type = "A"
    }

    routing_policy = "MULTIVALUE"
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}
