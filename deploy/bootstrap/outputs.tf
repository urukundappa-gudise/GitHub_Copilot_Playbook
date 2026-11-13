output "ecr_repository_name" {
  value = aws_ecr_repository.application.name
}

output "ecr_repository_url" {
  value = aws_ecr_repository.application.repository_url
}

output "github_deployment_role_arn" {
  value = aws_iam_role.github_deployment.arn
}

output "apprunner_ecr_access_role_arn" {
  value = aws_iam_role.apprunner_ecr_access.arn
}

output "apprunner_instance_role_arn" {
  value = aws_iam_role.apprunner_instance.arn
}

output "ecs_subnet_ids" {
  value = aws_subnet.ecs_public[*].id
}

output "ecs_execution_role_arn" {
  value = try(aws_iam_role.ecs_execution[0].arn, null)
}

output "ecs_infrastructure_role_arn" {
  value = try(aws_iam_role.ecs_infrastructure[0].arn, null)
}
