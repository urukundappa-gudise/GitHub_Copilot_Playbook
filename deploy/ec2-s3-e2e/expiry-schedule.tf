resource "aws_iam_role" "expiry_stop" {
  name = "${local.name_prefix}-expiry-stop"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = local.common_tags
}

resource "aws_iam_role_policy" "expiry_stop" {
  name = "stop-only-this-stack-instance"
  role = aws_iam_role.expiry_stop.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ec2:StopInstances"]
      Resource = aws_instance.api.arn
    }]
  })
}

resource "aws_scheduler_schedule" "stop_instance" {
  name                         = "${local.name_prefix}-stop-at-68-hours"
  description                  = "Stop the E2E API before its 72-hour expiry."
  schedule_expression          = "at(${formatdate("YYYY-MM-DD'T'HH:mm:ss", local.stop_at)})"
  schedule_expression_timezone = "UTC"
  action_after_completion      = "DELETE"
  flexible_time_window { mode = "OFF" }
  target {
    arn      = "arn:${data.aws_partition.current.partition}:scheduler:::aws-sdk:ec2:stopInstances"
    role_arn = aws_iam_role.expiry_stop.arn
    input = jsonencode({
      InstanceIds = [aws_instance.api.id]
    })
    retry_policy {
      maximum_event_age_in_seconds = 86400
      maximum_retry_attempts       = 185
    }
  }
}
