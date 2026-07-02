variable "region" {
  description = "AWS region for the SageMaker endpoint."
  type        = string
  default     = "us-east-2"
}

variable "name_prefix" {
  description = "Prefix for SageMaker resource names."
  type        = string
  default     = "coder-vllm"
}

variable "model_id" {
  description = "Hugging Face model ID served by the SageMaker vLLM endpoint."
  type        = string
  default     = "Qwen/Qwen2.5-Coder-32B-Instruct-AWQ"
}

variable "instance_type" {
  description = "SageMaker real-time endpoint instance type."
  type        = string
  default     = "ml.g5.12xlarge"
}

variable "initial_instance_count" {
  description = "Number of SageMaker instances behind the endpoint."
  type        = number
  default     = 1
}

variable "dlc_account_id" {
  description = "AWS Deep Learning Containers ECR account ID."
  type        = string
  default     = "763104351884"
}

variable "djl_image_tag" {
  description = "DJL/LMI image tag with vLLM support."
  type        = string
  default     = "0.36.0-lmi26.0.0-cu130"
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

variable "trust_remote_code" {
  description = "Whether to allow remote model code."
  type        = bool
  default     = false
}

variable "hugging_face_hub_token" {
  description = "Optional Hugging Face token for gated models."
  type        = string
  default     = ""
  sensitive   = true
}
