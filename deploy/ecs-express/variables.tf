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
  type    = string
  default = "demo"
}
