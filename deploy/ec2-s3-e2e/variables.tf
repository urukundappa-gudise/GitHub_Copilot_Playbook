variable "aws_region" {
  type = string
}

variable "stack_id" {
  description = "Unique lowercase identifier for this isolated E2E stack."
  type        = string
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{2,23}$", var.stack_id))
    error_message = "stack_id must be 3-24 lowercase letters, digits, or hyphens."
  }
}

variable "owner" {
  description = "Operator email or team alias used for expiry alerts."
  type        = string
  validation {
    condition     = length(trimspace(var.owner)) > 2
    error_message = "owner must identify a person or team who can remove expired infrastructure."
  }
}

variable "app_domain_name" {
  description = "HTTPS frontend hostname managed by the organization's existing DNS provider."
  type        = string
  default     = "adlc.infovision.com"
  validation {
    condition     = lower(var.app_domain_name) == "adlc.infovision.com"
    error_message = "app_domain_name must be the operator-approved adlc.infovision.com hostname."
  }
}

variable "api_domain_name" {
  description = "HTTPS API origin hostname managed by the organization's existing DNS provider."
  type        = string
  default     = "ai.adlc.infovision.com"
  validation {
    condition     = lower(var.api_domain_name) == "ai.adlc.infovision.com"
    error_message = "api_domain_name must be the operator-approved ai.adlc.infovision.com hostname."
  }
}

variable "cloudfront_certificate_arn" {
  description = "ACM certificate for app_domain_name, issued in us-east-1."
  type        = string
  validation {
    condition     = can(regex("^arn:[^:]+:acm:us-east-1:[0-9]{12}:certificate/.+$", var.cloudfront_certificate_arn))
    error_message = "CloudFront requires an ACM certificate ARN from us-east-1."
  }
}

variable "alb_certificate_arn" {
  description = "ACM certificate for api_domain_name in aws_region."
  type        = string
  validation {
    condition     = can(regex("^arn:[^:]+:acm:${var.aws_region}:[0-9]{12}:certificate/.+$", var.alb_certificate_arn))
    error_message = "The ALB certificate must be issued in aws_region."
  }
}

variable "allowed_client_cidrs" {
  description = "IPv4 client CIDRs permitted by the CloudFront WAF allow-list."
  type        = list(string)
  validation {
    condition     = length(var.allowed_client_cidrs) > 0 && alltrue([for cidr in var.allowed_client_cidrs : can(cidrnetmask(cidr))])
    error_message = "At least one valid client IPv4 CIDR is required; use narrow approved ranges."
  }
}

variable "image_uri" {
  description = "Immutable ECR image URI tagged with the full 40-character commit SHA."
  type        = string
  validation {
    condition     = can(regex("^[0-9]{12}\\.dkr\\.ecr\\.${var.aws_region}\\.amazonaws\\.com/.+:[a-f0-9]{40}$", var.image_uri))
    error_message = "image_uri must be in aws_region and pinned to a full commit SHA."
  }
}

variable "ecr_repository_arn" {
  description = "Exact ECR repository ARN allowed to the EC2 runtime role."
  type        = string
  validation {
    condition     = can(regex("^arn:[^:]+:ecr:${var.aws_region}:[0-9]{12}:repository/.+$", var.ecr_repository_arn))
    error_message = "ecr_repository_arn must identify a repository in aws_region."
  }
}

variable "azure_ad_tenant_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$", var.azure_ad_tenant_id))
    error_message = "azure_ad_tenant_id must be an Entra tenant GUID."
  }
}

variable "azure_ad_client_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$", var.azure_ad_client_id))
    error_message = "azure_ad_client_id must be an Entra application GUID."
  }
}

variable "azure_ad_redirect_uri" {
  type = string
  validation {
    condition     = var.azure_ad_redirect_uri == "https://${var.app_domain_name}/api/v1/auth/callback"
    error_message = "The Entra callback must exactly match the app hostname and /api/v1/auth/callback path."
  }
}

variable "azure_ad_post_logout_redirect_uri" {
  type = string
  validation {
    condition     = var.azure_ad_post_logout_redirect_uri == "https://${var.app_domain_name}/"
    error_message = "The Entra post-logout URI must exactly match the HTTPS app origin."
  }
}

variable "azure_ad_client_secret_arn" {
  description = "Operator-managed Entra client secret ARN; never the secret value."
  type        = string
  validation {
    condition     = can(regex("^arn:[^:]+:secretsmanager:${var.aws_region}:[0-9]{12}:secret:.+$", var.azure_ad_client_secret_arn))
    error_message = "azure_ad_client_secret_arn must be a Secrets Manager ARN in aws_region."
  }
}

variable "database_username" {
  description = "Non-secret RDS master username; RDS manages the password in Secrets Manager."
  type        = string
  default     = "aimplify_e2e"
  validation {
    condition     = can(regex("^[A-Za-z][A-Za-z0-9_]{0,62}$", var.database_username))
    error_message = "database_username must be a valid PostgreSQL username."
  }
}

variable "expires_after_hours" {
  description = "Fixed maximum lifetime for this disposable stack."
  type        = number
  default     = 72
  validation {
    condition     = var.expires_after_hours == 72
    error_message = "E2E stack lifetime is fixed at 72 hours; request a new isolated stack for longer testing."
  }
}

variable "vpc_cidr" {
  type    = string
  default = "10.240.0.0/16"
}

variable "instance_type" {
  type    = string
  default = "t3.small"
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "registry_prefix" {
  description = "Prefix for expiry manifests in the operator-provisioned state bucket."
  type        = string
  default     = "e2e-sso/registry"
  validation {
    condition     = startswith(var.registry_prefix, "e2e-sso/") && !strcontains(var.registry_prefix, "..")
    error_message = "registry_prefix must stay under the isolated e2e-sso/ prefix."
  }
}

variable "expiry_alert_topic_arn" {
  description = "Pre-existing SNS topic ARN outside this stack; it must survive teardown."
  type        = string
  validation {
    condition     = can(regex("^arn:[^:]+:sns:${var.aws_region}:[0-9]{12}:.+$", var.expiry_alert_topic_arn))
    error_message = "expiry_alert_topic_arn must identify an SNS topic in aws_region outside this stack."
  }
}

variable "state_bucket_name" {
  description = "Operator-provisioned private versioned bucket used for isolated state and the expiry registry."
  type        = string
  validation {
    condition     = can(regex("^[a-z0-9.-]{3,63}$", var.state_bucket_name))
    error_message = "state_bucket_name must be an existing S3 bucket name."
  }
}

variable "state_key" {
  description = "Unique remote state key for this stack; must not overlap App Runner or ECS state."
  type        = string
  validation {
    condition     = var.state_key == "e2e-sso/stacks/${var.stack_id}/terraform.tfstate"
    error_message = "state_key must be under e2e-sso/stacks/<stack-id>/terraform.tfstate."
  }
}

variable "created_at" {
  description = "UTC creation time recorded to the isolated registry before Terraform apply."
  type        = string
  validation {
    condition     = can(regex("^20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$", var.created_at))
    error_message = "created_at must be a UTC timestamp in YYYY-MM-DDTHH:MM:SSZ format."
  }
}
