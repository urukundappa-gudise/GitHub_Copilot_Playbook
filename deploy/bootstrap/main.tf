data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  apprunner_service_arn = "arn:${data.aws_partition.current.partition}:apprunner:${var.aws_region}:${data.aws_caller_identity.current.account_id}:service/${var.apprunner_service_name}/*"
  apprunner_scaling_arn = "arn:${data.aws_partition.current.partition}:apprunner:${var.aws_region}:${data.aws_caller_identity.current.account_id}:autoscalingconfiguration/${var.apprunner_service_name}-single/*/*"
  github_oidc_subject = var.github_identity_ids == null ? (
    "repo:${var.github_repository}:ref:${var.github_ref}"
    ) : (
    "repo:${split("/", var.github_repository)[0]}@${var.github_identity_ids.owner_id}/${split("/", var.github_repository)[1]}@${var.github_identity_ids.repository_id}:ref:${var.github_ref}"
  )
  terraform_state_objects = [
    var.bootstrap_state_key,
    "${var.bootstrap_state_key}.tflock",
    var.apprunner_state_key,
    "${var.apprunner_state_key}.tflock",
  ]
}

resource "aws_ecr_repository" "application" {
  name                 = var.ecr_repository_name
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = {
    Environment = var.deployment_environment
    ManagedBy   = "terraform"
    Service     = var.apprunner_service_name
  }
}

data "aws_iam_policy_document" "github_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [var.github_oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [local.github_oidc_subject]
    }
  }
}

resource "aws_iam_role" "github_deployment" {
  name                 = var.deployment_role_name
  assume_role_policy   = data.aws_iam_policy_document.github_trust.json
  max_session_duration = 3600

  tags = {
    Environment = var.deployment_environment
    ManagedBy   = "terraform"
  }
}

data "aws_iam_policy_document" "github_permissions" {
  statement {
    sid       = "GetDeploymentAccountIdentity"
    effect    = "Allow"
    actions   = ["sts:GetCallerIdentity"]
    resources = ["*"]
  }

  statement {
    sid       = "ECRAuthorization"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid    = "PushApplicationImage"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:CompleteLayerUpload",
      "ecr:DescribeImages",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
    resources = [aws_ecr_repository.application.arn]
  }

  statement {
    sid       = "CreateNamedAppRunnerService"
    effect    = "Allow"
    actions   = ["apprunner:CreateService"]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/Service"
      values   = [var.apprunner_service_name]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/Name"
      values   = [var.apprunner_service_name]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/ManagedBy"
      values   = ["terraform"]
    }
  }

  statement {
    sid       = "CreateNamedScalingConfiguration"
    effect    = "Allow"
    actions   = ["apprunner:CreateAutoScalingConfiguration"]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/Service"
      values   = [var.apprunner_service_name]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/Name"
      values   = ["${var.apprunner_service_name}-single"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/ManagedBy"
      values   = ["terraform"]
    }
  }

  statement {
    sid       = "ListScalingConfigurationsInRegion"
    effect    = "Allow"
    actions   = ["apprunner:ListAutoScalingConfigurations"]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = [var.aws_region]
    }
  }

  statement {
    sid    = "ManageOnlyNamedAppRunnerService"
    effect = "Allow"
    actions = [
      "apprunner:DeleteService",
      "apprunner:DescribeService",
      "apprunner:ListTagsForResource",
      "apprunner:StartDeployment",
      "apprunner:TagResource",
      "apprunner:UntagResource",
      "apprunner:UpdateService",
    ]
    resources = [local.apprunner_service_arn]
  }

  statement {
    sid    = "ManageScalingConfiguration"
    effect = "Allow"
    actions = [
      "apprunner:DeleteAutoScalingConfiguration",
      "apprunner:DescribeAutoScalingConfiguration",
      "apprunner:ListTagsForResource",
      "apprunner:TagResource",
      "apprunner:UntagResource",
    ]
    resources = [local.apprunner_scaling_arn]
  }

  statement {
    sid       = "PassOnlyAppRunnerECRAccessRole"
    effect    = "Allow"
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.apprunner_ecr_access.arn]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["build.apprunner.amazonaws.com"]
    }
  }

  statement {
    sid       = "ReadTerraformStateBucketMetadata"
    effect    = "Allow"
    actions   = ["s3:GetBucketLocation", "s3:GetBucketVersioning"]
    resources = ["arn:${data.aws_partition.current.partition}:s3:::${var.state_bucket_name}"]
  }

  statement {
    sid       = "ListOnlyTerraformStatePrefixes"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = ["arn:${data.aws_partition.current.partition}:s3:::${var.state_bucket_name}"]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = local.terraform_state_objects
    }
  }

  statement {
    sid    = "ReadAndWriteOnlyTerraformStateObjects"
    effect = "Allow"
    actions = [
      "s3:DeleteObject",
      "s3:GetObject",
      "s3:PutObject",
    ]
    resources = [
      for key in local.terraform_state_objects :
      "arn:${data.aws_partition.current.partition}:s3:::${var.state_bucket_name}/${key}"
    ]
  }
}

resource "aws_iam_policy" "github_permissions" {
  name   = "${var.deployment_role_name}-policy"
  policy = data.aws_iam_policy_document.github_permissions.json
}

resource "aws_iam_role_policy_attachment" "github_permissions" {
  role       = aws_iam_role.github_deployment.name
  policy_arn = aws_iam_policy.github_permissions.arn
}

data "aws_iam_policy_document" "apprunner_ecr_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["build.apprunner.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = [local.apprunner_service_arn]
    }
  }
}

resource "aws_iam_role" "apprunner_ecr_access" {
  name               = var.ecr_access_role_name
  assume_role_policy = data.aws_iam_policy_document.apprunner_ecr_trust.json

  tags = {
    Environment = var.deployment_environment
    ManagedBy   = "terraform"
    Service     = var.apprunner_service_name
  }
}

data "aws_iam_policy_document" "apprunner_ecr_read" {
  statement {
    sid       = "ECRAuthorization"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid    = "PullApplicationImage"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = [aws_ecr_repository.application.arn]
  }
}

resource "aws_iam_policy" "apprunner_ecr_read" {
  name   = "${var.ecr_access_role_name}-policy"
  policy = data.aws_iam_policy_document.apprunner_ecr_read.json
}

resource "aws_iam_role_policy_attachment" "apprunner_ecr_read" {
  role       = aws_iam_role.apprunner_ecr_access.name
  policy_arn = aws_iam_policy.apprunner_ecr_read.arn
}
