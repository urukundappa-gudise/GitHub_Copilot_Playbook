data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_vpc" "ecs" {
  count                = var.enable_ecs_express ? 1 : 0
  cidr_block           = "10.80.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name        = "${var.ecs_cluster_name}-vpc"
    Environment = var.deployment_environment
    ManagedBy   = "terraform"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_internet_gateway" "ecs" {
  count  = var.enable_ecs_express ? 1 : 0
  vpc_id = aws_vpc.ecs[0].id
}

resource "aws_subnet" "ecs_public" {
  count                   = var.enable_ecs_express ? 2 : 0
  vpc_id                  = aws_vpc.ecs[0].id
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  cidr_block              = cidrsubnet(aws_vpc.ecs[0].cidr_block, 8, count.index)
  map_public_ip_on_launch = true

  tags = {
    Name        = "${var.ecs_cluster_name}-public-${count.index + 1}"
    Environment = var.deployment_environment
    ManagedBy   = "terraform"
  }
}

resource "aws_route_table" "ecs_public" {
  count  = var.enable_ecs_express ? 1 : 0
  vpc_id = aws_vpc.ecs[0].id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.ecs[0].id
  }
}

resource "aws_route_table_association" "ecs_public" {
  count          = var.enable_ecs_express ? 2 : 0
  subnet_id      = aws_subnet.ecs_public[count.index].id
  route_table_id = aws_route_table.ecs_public[0].id
}

resource "aws_ecs_cluster" "express" {
  count = var.enable_ecs_express ? 1 : 0
  name  = var.ecs_cluster_name

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_ecs_cluster_capacity_providers" "express" {
  count              = var.enable_ecs_express ? 1 : 0
  cluster_name       = aws_ecs_cluster.express[0].name
  capacity_providers = ["FARGATE"]
}

data "aws_iam_policy_document" "ecs_execution_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecs_execution" {
  count              = var.enable_ecs_express ? 1 : 0
  name               = "${var.ecs_cluster_name}-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_execution_trust.json

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  count      = var.enable_ecs_express ? 1 : 0
  role       = aws_iam_role.ecs_execution[0].name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "ecs_secret_read" {
  count = var.enable_ecs_express && var.azure_ad_client_secret_arn != null ? 1 : 0

  statement {
    sid       = "ReadConfiguredEntraClientSecret"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.azure_ad_client_secret_arn]
  }
}

resource "aws_iam_role_policy" "ecs_secret_read" {
  count  = var.enable_ecs_express && var.azure_ad_client_secret_arn != null ? 1 : 0
  name   = "${var.ecs_cluster_name}-read-entra-secret"
  role   = aws_iam_role.ecs_execution[0].name
  policy = data.aws_iam_policy_document.ecs_secret_read[0].json
}

data "aws_iam_policy_document" "ecs_database_secret_read" {
  count = var.enable_ecs_express && try(trimspace(var.database_url_secret_arn), "") != "" ? 1 : 0

  statement {
    sid       = "ReadConfiguredDatabaseUrl"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.database_url_secret_arn]
  }
}

resource "aws_iam_role_policy" "ecs_database_secret_read" {
  count  = var.enable_ecs_express && try(trimspace(var.database_url_secret_arn), "") != "" ? 1 : 0
  name   = "${var.ecs_cluster_name}-read-database-url"
  role   = aws_iam_role.ecs_execution[0].name
  policy = data.aws_iam_policy_document.ecs_database_secret_read[0].json
}

data "aws_iam_policy_document" "ecs_infrastructure_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecs_infrastructure" {
  count              = var.enable_ecs_express ? 1 : 0
  name               = "${var.ecs_cluster_name}-infrastructure"
  assume_role_policy = data.aws_iam_policy_document.ecs_infrastructure_trust.json

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_role_policy_attachment" "ecs_infrastructure" {
  count      = var.enable_ecs_express ? 1 : 0
  role       = aws_iam_role.ecs_infrastructure[0].name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AmazonECSInfrastructureRoleforExpressGatewayServices"
}
