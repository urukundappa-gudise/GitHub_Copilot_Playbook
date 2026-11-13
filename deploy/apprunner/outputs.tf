output "service_arn" {
  description = "ARN used by deployment automation to wait for App Runner status."
  value       = aws_apprunner_service.application.arn
}

output "service_url" {
  description = "AWS-assigned HTTPS URL for the public demo."
  value       = "https://${aws_apprunner_service.application.service_url}"
}
