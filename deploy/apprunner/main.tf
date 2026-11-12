data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

resource "aws_apprunner_auto_scaling_configuration_version" "demo" {
  auto_scaling_configuration_name = "${var.service_name}-single-instance"
  max_concurrency                 = 100
  max_size                        = 1
  min_size                        = 1

  tags = {
    Environment = var.deployment_environment
    ManagedBy   = "terraform"
    Name        = "${var.service_name}-single-instance"
    Service     = var.service_name
  }

  lifecycle {
    create_before_destroy = true
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
          AUTH_REQUIRED = "false"
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
    cpu    = "0.25 vCPU"
    memory = "0.5 GB"
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
