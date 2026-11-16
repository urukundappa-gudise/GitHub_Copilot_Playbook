resource "aws_db_instance" "sessions" {
  identifier                  = "${local.name_prefix}-sessions"
  engine                      = "postgres"
  engine_version              = "16"
  instance_class              = var.db_instance_class
  allocated_storage           = 20
  max_allocated_storage       = 20
  storage_type                = "gp3"
  storage_encrypted           = true
  db_name                     = "aimplify"
  username                    = var.database_username
  manage_master_user_password = true
  db_subnet_group_name        = aws_db_subnet_group.sessions.name
  vpc_security_group_ids      = [aws_security_group.database.id]
  publicly_accessible         = false
  multi_az                    = false
  backup_retention_period     = 0
  auto_minor_version_upgrade  = true
  deletion_protection         = false
  skip_final_snapshot         = true
  apply_immediately           = true
  tags                        = local.common_tags
}

resource "aws_iam_role" "api" {
  name = "${local.name_prefix}-api-instance"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.api.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "api_runtime" {
  name = "${local.name_prefix}-runtime-read"
  role = aws_iam_role.api.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "EcrAuth"
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Sid    = "PullOnlyConfiguredImageRepository"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
        ]
        Resource = var.ecr_repository_arn
      },
      {
        Sid      = "ReadOnlyConfiguredRuntimeSecrets"
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = [var.azure_ad_client_secret_arn, local.db_secret_arn]
      },
    ]
  })
}

resource "aws_iam_instance_profile" "api" {
  name = "${local.name_prefix}-api"
  role = aws_iam_role.api.name
  tags = local.common_tags
}

resource "aws_instance" "api" {
  ami                         = data.aws_ssm_parameter.al2023_ami.value
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.private[0].id
  vpc_security_group_ids      = [aws_security_group.api.id]
  iam_instance_profile        = aws_iam_instance_profile.api.name
  associate_public_ip_address = false
  user_data_replace_on_change = false
  user_data = templatefile("${path.module}/bootstrap.sh.tftpl", {
    aws_region                        = var.aws_region
    app_origin                        = "https://${var.app_domain_name}"
    image_uri                         = var.image_uri
    azure_ad_tenant_id                = var.azure_ad_tenant_id
    azure_ad_client_id                = var.azure_ad_client_id
    azure_ad_redirect_uri             = var.azure_ad_redirect_uri
    azure_ad_post_logout_redirect_uri = var.azure_ad_post_logout_redirect_uri
    azure_ad_client_secret_arn        = var.azure_ad_client_secret_arn
    database_secret_arn               = local.db_secret_arn
    database_host                     = aws_db_instance.sessions.address
  })
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
    instance_metadata_tags      = "disabled"
  }
  root_block_device {
    encrypted             = true
    volume_type           = "gp3"
    volume_size           = 16
    delete_on_termination = true
  }
  instance_initiated_shutdown_behavior = "stop"
  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-api"
  })
  depends_on = [
    aws_vpc_endpoint.interface,
    aws_vpc_endpoint.s3,
    aws_db_instance.sessions,
  ]
}
