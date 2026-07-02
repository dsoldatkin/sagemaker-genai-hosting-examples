variable "region" {
  description = "AWS region for the G6e endpoint."
  type        = string
  default     = "us-east-2"
}

variable "name_prefix" {
  description = "Prefix for AWS resource names."
  type        = string
  default     = "coder-gateway"
}

variable "instance_type" {
  description = "G6e instance type for the single-GPU coder endpoint."
  type        = string
  default     = "g6e.2xlarge"
}

variable "allowed_cidr" {
  description = "CIDR allowed to call the test gateway and vLLM endpoints."
  type        = string
}

variable "vpc_id" {
  description = "Optional VPC ID. Defaults to the region's default VPC."
  type        = string
  default     = null
}

variable "subnet_id" {
  description = "Optional subnet ID. Defaults to the first default subnet found."
  type        = string
  default     = null
}

variable "root_volume_size_gb" {
  description = "Root EBS volume size. Needs room for model cache and Docker images."
  type        = number
  default     = 500
}

variable "model_id" {
  description = "Hugging Face model ID served by vLLM."
  type        = string
  default     = "Qwen/Qwen2.5-Coder-32B-Instruct-AWQ"
}

variable "served_model_name" {
  description = "Model name exposed by vLLM and LiteLLM."
  type        = string
  default     = "coding-local"
}

variable "max_model_len" {
  description = "Initial context length for vLLM."
  type        = number
  default     = 32768
}

variable "gpu_memory_utilization" {
  description = "vLLM GPU memory utilization target."
  type        = number
  default     = 0.90
}

variable "vllm_image" {
  description = "vLLM OpenAI server container image."
  type        = string
  default     = "vllm/vllm-openai:v0.8.5"
}

variable "litellm_image" {
  description = "LiteLLM proxy container image."
  type        = string
  default     = "ghcr.io/berriai/litellm:main-v1.67.0"
}

variable "hugging_face_hub_token" {
  description = "Optional Hugging Face token for gated models."
  type        = string
  default     = ""
  sensitive   = true
}

variable "litellm_master_key" {
  description = "Optional LiteLLM master key. If unset, Terraform generates one."
  type        = string
  default     = null
  sensitive   = true
}

variable "associate_public_ip" {
  description = "Whether to assign a public IP to the instance. Set to false and use SSM Session Manager for access in production."
  type        = bool
  default     = false
}
