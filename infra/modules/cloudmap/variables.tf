variable "vpc_id" {
  type        = string
  description = "ID of the VPC for the private DNS namespace."
}

variable "namespace_name" {
  type        = string
  default     = "switchboard.local"
  description = "Private DNS namespace name for MCP server discovery (D-07)."
}

variable "service_names" {
  type        = list(string)
  default     = ["sb-echo", "sb-ping"]
  description = "Cloud Map service names for MCP server discovery. Each name becomes resolvable as <name>.<namespace>."
}
