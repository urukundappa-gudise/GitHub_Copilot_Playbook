variable "aws_region" {
  type = string
}

variable "service_name" {
  type = string
}

variable "cluster_name" {
  type = string
}

variable "ecr_repository_name" {
  type = string
}

variable "image_tag" {
  type = string
  validation {
    condition     = can(regex("^[a-f0-9]{40}$", var.image_tag))
    error_message = "image_tag must be the full Git commit SHA."
  }
}

variable "execution_role_arn" {
  type = string
}

variable "infrastructure_role_arn" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
  validation {
    condition     = length(var.subnet_ids) >= 2
    error_message = "At least two public subnets in distinct availability zones are required."
  }
}

variable "deployment_environment" {
  description = "Runtime environment; public demos remain unauthenticated while production requires SSO."
  type        = string
  default     = "demo"

  validation {
    condition     = contains(["demo", "production"], var.deployment_environment)
    error_message = "deployment_environment must be demo or production."
  }
}

variable "azure_ad_client_secret_arn" {
  description = "Operator-managed Entra client secret ARN; never provide the secret value."
  type        = string
  default     = null
}

variable "azure_ad_tenant_id" {
  description = "Entra tenant ID used for OIDC discovery."
  type        = string
  default     = ""
}

variable "azure_ad_client_id" {
  description = "Entra application client ID."
  type        = string
  default     = ""
}

variable "azure_ad_redirect_uri" {
  description = "Exact registered OIDC callback URL."
  type        = string
  default     = ""
}

variable "azure_ad_post_logout_redirect_uri" {
  description = "Exact registered post-logout redirect URL."
  type        = string
  default     = ""
}
