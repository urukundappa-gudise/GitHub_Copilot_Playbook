variable "aws_region" {
  description = "AWS region for ECR and App Runner."
  type        = string
}

variable "github_oidc_provider_arn" {
  description = "ARN of the account's token.actions.githubusercontent.com OIDC provider."
  type        = string
}

variable "github_repository" {
  description = "GitHub owner/repository allowed to deploy."
  type        = string
  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository must be in owner/repository format."
  }
}

variable "github_identity_ids" {
  description = "GitHub owner and repository IDs for immutable OIDC subjects, or null for legacy name-only subjects."
  type = object({
    owner_id      = string
    repository_id = string
  })
  default = null

  validation {
    condition = var.github_identity_ids == null ? true : (
      can(regex("^[1-9][0-9]*$", var.github_identity_ids.owner_id)) &&
      can(regex("^[1-9][0-9]*$", var.github_identity_ids.repository_id))
    )
    error_message = "github_identity_ids must contain positive numeric owner_id and repository_id values."
  }
}

variable "github_ref" {
  description = "Exact Git ref authorized by the OIDC trust policy."
  type        = string
  default     = "refs/heads/main"
  validation {
    condition     = startswith(var.github_ref, "refs/heads/") || startswith(var.github_ref, "refs/tags/")
    error_message = "github_ref must be a fully qualified branch or tag ref."
  }
}

variable "deployment_environment" {
  description = "Environment label attached to deployment resources."
  type        = string
  default     = "demo"
}

variable "ecr_repository_name" {
  description = "Name of the immutable ECR image repository."
  type        = string
  default     = "aimplify-intake"
}

variable "apprunner_service_name" {
  description = "Exact App Runner service name the deployment role may manage."
  type        = string
  default     = "aimplify-intake-demo"

  validation {
    condition     = can(regex("^[A-Za-z0-9][A-Za-z0-9_-]{3,24}$", var.apprunner_service_name))
    error_message = "apprunner_service_name must be 4-25 characters, start with a letter or digit, and contain only letters, digits, hyphens, or underscores."
  }
}

variable "deployment_role_name" {
  description = "Name of the GitHub Actions deployment role."
  type        = string
  default     = "aimplify-github-deploy"
}

variable "ecr_access_role_name" {
  description = "Name of the App Runner ECR image-pull role."
  type        = string
  default     = "aimplify-apprunner-ecr-access"
}

variable "state_bucket_name" {
  description = "Pre-provisioned S3 bucket containing Terraform state."
  type        = string
}

variable "bootstrap_state_key" {
  description = "Exact S3 object key for bootstrap Terraform state."
  type        = string
  default     = "apprunner/bootstrap.tfstate"
}

variable "apprunner_state_key" {
  description = "Exact S3 object key for App Runner service Terraform state."
  type        = string
  default     = "apprunner/service.tfstate"
}

variable "enable_ecs_express" {
  description = "Create a dedicated VPC and IAM roles for the ECS Express demo."
  type        = bool
  default     = false
}

variable "ecs_cluster_name" {
  description = "Dedicated ECS cluster for the Express demo."
  type        = string
  default     = "aimplify-intake-demo"
}

variable "ecs_state_key" {
  description = "Exact S3 object key for ECS Express service Terraform state."
  type        = string
  default     = "ecs-express/service.tfstate"
}
