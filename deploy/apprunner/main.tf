data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

resource "aws_apprunner_auto_scaling_configuration_version" "demo" {
  auto_scaling_configuration_name = "${var.service_name}-single"
  max_concurrency                 = 100
  max_size                        = 1
  min_size                        = 1

  tags = {
    Environment = var.deployment_environment
    ManagedBy   = "terraform"
    Name        = "${var.service_name}-single"
    Service     = var.service_name
  }

  lifecycle {
    create_before_destroy = true

    precondition {
      condition = var.deployment_environment != "production" || (
        var.apprunner_instance_role_arn != null
        && var.azure_ad_client_secret_arn != null
        && trimspace(var.azure_ad_tenant_id) != ""
        && trimspace(var.azure_ad_client_id) != ""
        && can(regex("^https://[^/?#]+$", trimspace(var.app_origin)))
        && startswith(var.azure_ad_redirect_uri, "https://")
        && startswith(var.azure_ad_post_logout_redirect_uri, "https://")
      )
      error_message = "Production App Runner requires an HTTPS origin, complete Entra settings, the operator-managed secret ARN, and an instance role."
    }
  }
}

resource "aws_apprunner_service" "application" {
  service_name = var.service_name

  auto_scaling_configuration_arn = aws_apprunner_auto_scaling_configuration_version.demo.arn

  source_configuration {
    auto_deployments_enabled = false

    authentication_configuration {
      access_role_arn = var.ecr_access_role_arn
    }

    image_repository {
      image_identifier      = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.aws_region}.${data.aws_partition.current.dns_suffix}/${var.ecr_repository_name}:${var.image_tag}"
      image_repository_type = "ECR"

      image_configuration {
        port = "8000"
        runtime_environment_variables = {
          APP_ENV                           = var.deployment_environment
          AUTH_REQUIRED                     = var.deployment_environment == "production" ? "true" : "false"
          AUTH_MOCK_MODE                    = "false"
          APP_ORIGIN                        = var.app_origin
          AZURE_AD_TENANT_ID                = var.azure_ad_tenant_id
          AZURE_AD_CLIENT_ID                = var.azure_ad_client_id
          AZURE_AD_REDIRECT_URI             = var.azure_ad_redirect_uri
          AZURE_AD_POST_LOGOUT_REDIRECT_URI = var.azure_ad_post_logout_redirect_uri
        }
        runtime_environment_secrets = var.azure_ad_client_secret_arn == null ? {} : {
          AZURE_AD_CLIENT_SECRET = var.azure_ad_client_secret_arn
        }
      }
    }
  }

  health_check_configuration {
    healthy_threshold   = 1
    interval            = 10
    path                = "/health/live"
    protocol            = "HTTP"
    timeout             = 5
    unhealthy_threshold = 5
  }

  instance_configuration {
    cpu               = "0.25 vCPU"
    memory            = "0.5 GB"
    instance_role_arn = var.azure_ad_client_secret_arn == null ? null : var.apprunner_instance_role_arn
  }

  network_configuration {
    egress_configuration {
      egress_type = "DEFAULT"
    }

    ingress_configuration {
      is_publicly_accessible = true
    }
  }

  tags = {
    Environment = var.deployment_environment
    ManagedBy   = "terraform"
    Name        = var.service_name
    Service     = var.service_name
  }
}
