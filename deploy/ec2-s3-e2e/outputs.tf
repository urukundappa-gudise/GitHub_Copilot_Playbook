output "app_url" {
  value       = "https://${var.app_domain_name}"
  description = "HTTPS URL for the private-S3 React application."
}

output "api_origin_url" {
  value       = "https://${var.api_domain_name}"
  description = "HTTPS API hostname to create in the existing Infovision DNS provider."
}

output "app_dns_cname_target" {
  value       = aws_cloudfront_distribution.app.domain_name
  description = "CNAME target for adlc.infovision.com in the existing Infovision DNS provider."
}

output "api_dns_cname_target" {
  value       = aws_lb.api.dns_name
  description = "CNAME target for ai.adlc.infovision.com in the existing Infovision DNS provider."
}

output "cloudfront_distribution_id" {
  value = aws_cloudfront_distribution.app.id
}

output "frontend_bucket_name" {
  value = aws_s3_bucket.frontend.id
}

output "api_instance_id" {
  value = aws_instance.api.id
}

output "database_endpoint" {
  value       = aws_db_instance.sessions.address
  description = "Private PostgreSQL endpoint; never publish this endpoint publicly."
}

output "expires_at" {
  value       = local.expires_at
  description = "The fail-closed cutoff and mandatory teardown deadline for this isolated stack."
}

output "state_key" {
  value       = var.state_key
  description = "Unique Terraform state key reserved for this stack."
}
