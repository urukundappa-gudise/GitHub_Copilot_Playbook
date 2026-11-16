variable "aws_region" {
  description = "AWS region containing the ECR repository and App Runner service."
  type        = string
}

variable "ecr_repository_name" {
  description = "Pre-provisioned immutable ECR repository name."
  type        = string
}

variable "image_tag" {
  description = "Immutable commit SHA tag already pushed to ECR."
  type        = string
  validation {
    condition     = can(regex("^[0-9a-f]{40}$", var.image_tag))
    error_message = "image_tag must be a full 40-character lowercase commit SHA."
  }
}

variable "service_name" {
  description = "AWS App Runner service name."
  type        = string
  default     = "aimplify-intake-demo"

  validation {
    condition     = can(regex("^[A-Za-z0-9][A-Za-z0-9_-]{3,24}$", var.service_name))
    error_message = "service_name must be 4-25 characters, start with a letter or digit, and contain only letters, digits, hyphens, or underscores."
  }
}

variable "ecr_access_role_arn" {
  description = "Bootstrap-provisioned App Runner ECR image-pull role ARN."
  type        = string
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

variable "apprunner_instance_role_arn" {
  description = "Bootstrap-provisioned App Runner instance role with access only to the configured client secret."
  type        = string
  default     = null
}

variable "app_origin" {
  description = "Approved HTTPS application origin without a trailing slash."
  type        = string
  default     = ""
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
