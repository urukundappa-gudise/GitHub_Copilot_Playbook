data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

resource "aws_ecs_express_gateway_service" "application" {
  cluster                 = var.cluster_name
  service_name            = var.service_name
  execution_role_arn      = var.execution_role_arn
  infrastructure_role_arn = var.infrastructure_role_arn
  cpu                     = "256"
  memory                  = "512"
  health_check_path       = "/health/live"
  wait_for_steady_state   = true

  primary_container {
    image          = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.aws_region}.${data.aws_partition.current.dns_suffix}/${var.ecr_repository_name}:${var.image_tag}"
    container_port = 8000

    environment {
      name  = "AUTH_REQUIRED"
      value = "false"
    }
  }

  network_configuration {
    subnets = var.subnet_ids
  }

  scaling_target {
    min_task_count = 1
    max_task_count = 1
  }

  tags = {
    Environment = var.deployment_environment
    ManagedBy   = "terraform"
    Name        = var.service_name
  }

  lifecycle {
    prevent_destroy = true
  }
}

output "service_arn" {
  value = aws_ecs_express_gateway_service.application.service_arn
}

output "ingress_paths" {
  value = aws_ecs_express_gateway_service.application.ingress_paths
}
