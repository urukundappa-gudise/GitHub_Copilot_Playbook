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
}

variable "ecr_access_role_arn" {
  description = "Bootstrap-provisioned App Runner ECR image-pull role ARN."
  type        = string
}

variable "deployment_environment" {
  description = "Deployment environment label."
  type        = string
  default     = "demo"
}
