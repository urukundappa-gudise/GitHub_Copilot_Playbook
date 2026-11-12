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
