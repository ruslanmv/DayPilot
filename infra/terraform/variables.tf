variable "aws_region" {
  description = "AWS region for DayPilot infrastructure."
  type        = string
  default     = "eu-west-1"
}

variable "project" {
  description = "Resource name prefix."
  type        = string
  default     = "daypilot"
}

variable "service_names" {
  description = "Containerized DayPilot services published to ECR."
  type        = list(string)
  default = [
    "api-gateway",
    "orchestrator",
    "mcp-host",
    "knowledge-service",
    "model-serving",
    "voice-gateway",
    "observability",
  ]
}
