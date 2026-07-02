output "instance_id" {
  description = "EC2 instance ID."
  value       = aws_instance.endpoint.id
}

output "public_ip" {
  description = "Public IP for the test endpoint."
  value       = aws_instance.endpoint.public_ip
}

output "gateway_base_url" {
  description = "OpenAI-compatible LiteLLM gateway base URL."
  value       = "http://${aws_instance.endpoint.public_ip}:4000/v1"
}

output "vllm_base_url" {
  description = "Direct vLLM OpenAI-compatible base URL for diagnostics."
  value       = "http://${aws_instance.endpoint.public_ip}:8000/v1"
}

output "litellm_api_key" {
  description = "LiteLLM API key for smoke tests and client config."
  value       = local.litellm_master_key
  sensitive   = true
}

output "ssm_start_session_command" {
  description = "Command to start an SSM shell on the instance."
  value       = "aws ssm start-session --target ${aws_instance.endpoint.id} --region ${var.region}"
}
