output "endpoint_name" {
  description = "SageMaker endpoint name."
  value       = aws_sagemaker_endpoint.vllm.name
}

output "model_name" {
  description = "SageMaker model name."
  value       = aws_sagemaker_model.vllm.name
}

output "endpoint_config_name" {
  description = "SageMaker endpoint configuration name."
  value       = aws_sagemaker_endpoint_configuration.vllm.name
}

output "image_uri" {
  description = "SageMaker inference image URI."
  value       = local.image_uri
}

output "region" {
  description = "AWS region."
  value       = var.region
}
