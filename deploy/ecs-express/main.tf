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
      name  = "APP_ENV"
      value = var.deployment_environment
    }

    environment {
      name  = "AUTH_REQUIRED"
      value = var.deployment_environment == "production" ? "true" : "false"
    }

    environment {
      name  = "AUTH_MOCK_MODE"
      value = "false"
    }

    environment {
      name  = "AZURE_AD_TENANT_ID"
      value = var.azure_ad_tenant_id
    }

    environment {
      name  = "AZURE_AD_CLIENT_ID"
      value = var.azure_ad_client_id
    }

    environment {
      name  = "AZURE_AD_REDIRECT_URI"
      value = var.azure_ad_redirect_uri
    }

    environment {
      name  = "AZURE_AD_POST_LOGOUT_REDIRECT_URI"
      value = var.azure_ad_post_logout_redirect_uri
    }

    dynamic "secret" {
      for_each = var.azure_ad_client_secret_arn == null ? [] : [var.azure_ad_client_secret_arn]

      content {
        name       = "AZURE_AD_CLIENT_SECRET"
        value_from = secret.value
      }
    }
  }

  network_configuration {
    subnets = var.subnet_ids
  }

  scaling_target {
    min_task_count            = 1
    max_task_count            = 1
    auto_scaling_metric       = "AVERAGE_CPU"
    auto_scaling_target_value = 60
  }

  tags = {
    Environment = var.deployment_environment
    ManagedBy   = "terraform"
    Name        = var.service_name
  }

  lifecycle {
    prevent_destroy = true

    precondition {
      condition = var.deployment_environment != "production" || (
        var.azure_ad_client_secret_arn != null
        && trimspace(var.azure_ad_tenant_id) != ""
        && trimspace(var.azure_ad_client_id) != ""
        && startswith(var.azure_ad_redirect_uri, "https://")
        && startswith(var.azure_ad_post_logout_redirect_uri, "https://")
      )
      error_message = "Production ECS Express requires complete Entra settings and the operator-managed secret ARN."
    }
  }
}

output "service_arn" {
  value = aws_ecs_express_gateway_service.application.service_arn
}

output "ingress_paths" {
  value = aws_ecs_express_gateway_service.application.ingress_paths
}
