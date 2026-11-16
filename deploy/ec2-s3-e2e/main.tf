data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_availability_zones" "available" {
  state = "available"
}
data "aws_ssm_parameter" "al2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

locals {
  name_prefix       = "${var.stack_id}-e2e"
  account_id        = data.aws_caller_identity.current.account_id
  expires_at        = timeadd(terraform_data.stack_clock.output.created_at, "${var.expires_after_hours}h")
  stop_at           = timeadd(terraform_data.stack_clock.output.created_at, "68h")
  frontend_bucket   = "${var.stack_id}-${local.account_id}-frontend"
  db_secret_arn     = aws_db_instance.sessions.master_user_secret[0].secret_arn
  cloudfront_prefix = data.aws_ec2_managed_prefix_list.cloudfront_origin.id
  common_tags = {
    Purpose   = "e2e-sso"
    StackId   = var.stack_id
    Owner     = var.owner
    ExpiresAt = local.expires_at
    ManagedBy = "terraform"
  }
}

resource "terraform_data" "stack_clock" {
  input = {
    created_at = var.created_at
  }

  lifecycle {
    ignore_changes = [input]
    precondition {
      condition     = timecmp(timeadd(var.created_at, "68h"), timeadd(timestamp(), "20m")) > 0
      error_message = "The registered E2E stack must be applied with at least 20 minutes before its hour-68 shutdown."
    }
  }
}

data "aws_ec2_managed_prefix_list" "cloudfront_origin" {
  name = "com.amazonaws.global.cloudfront.origin-facing"
}

resource "aws_s3_bucket" "frontend" {
  bucket        = local.frontend_bucket
  force_destroy = true
  tags          = local.common_tags
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket                  = aws_s3_bucket.frontend.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  rule {
    id     = "expire-e2e-assets"
    status = "Enabled"
    expiration { days = 4 }
    filter { prefix = "" }
    noncurrent_version_expiration { noncurrent_days = 4 }
  }
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "CloudFrontReadOnly"
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = ["s3:GetObject"]
      Resource  = "${aws_s3_bucket.frontend.arn}/*"
      Condition = { StringEquals = { "AWS:SourceArn" = aws_cloudfront_distribution.app.arn } }
    }]
  })
}

resource "aws_s3_object" "expiry_manifest" {
  bucket       = var.state_bucket_name
  key          = "${var.registry_prefix}/${var.stack_id}.json"
  content_type = "application/json"
  content = jsonencode({
    stack_id   = var.stack_id
    owner      = var.owner
    created_at = terraform_data.stack_clock.output.created_at
    expires_at = local.expires_at
    state_key  = var.state_key
    variables = {
      aws_region                        = var.aws_region
      stack_id                          = var.stack_id
      owner                             = var.owner
      app_domain_name                   = var.app_domain_name
      api_domain_name                   = var.api_domain_name
      cloudfront_certificate_arn        = var.cloudfront_certificate_arn
      alb_certificate_arn               = var.alb_certificate_arn
      allowed_client_cidrs              = var.allowed_client_cidrs
      image_uri                         = var.image_uri
      ecr_repository_arn                = var.ecr_repository_arn
      azure_ad_tenant_id                = var.azure_ad_tenant_id
      azure_ad_client_id                = var.azure_ad_client_id
      azure_ad_redirect_uri             = var.azure_ad_redirect_uri
      azure_ad_post_logout_redirect_uri = var.azure_ad_post_logout_redirect_uri
      azure_ad_client_secret_arn        = var.azure_ad_client_secret_arn
      database_username                 = var.database_username
      expires_after_hours               = var.expires_after_hours
      vpc_cidr                          = var.vpc_cidr
      instance_type                     = var.instance_type
      db_instance_class                 = var.db_instance_class
      registry_prefix                   = var.registry_prefix
      expiry_alert_topic_arn            = var.expiry_alert_topic_arn
      state_bucket_name                 = var.state_bucket_name
      state_key                         = var.state_key
    }
  })
  depends_on = [aws_s3_bucket_public_access_block.frontend]
}
