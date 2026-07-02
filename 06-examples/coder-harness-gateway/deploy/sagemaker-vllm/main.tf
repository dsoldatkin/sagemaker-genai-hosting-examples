resource "random_id" "suffix" {
  byte_length = 4
}

locals {
  resource_name = "${var.name_prefix}-${random_id.suffix.hex}"
  image_uri     = "${var.dlc_account_id}.dkr.ecr.${var.region}.amazonaws.com/djl-inference:${var.djl_image_tag}"
}

resource "aws_iam_role" "sagemaker_execution" {
  name = "${local.resource_name}-exec"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "sagemaker.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "sagemaker_execution" {
  name = "${local.resource_name}-policy"
  role = aws_iam_role.sagemaker_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:DescribeLogStreams",
          "logs:PutLogEvents"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "time_sleep" "iam_propagation" {
  create_duration = "60s"

  depends_on = [aws_iam_role_policy.sagemaker_execution]
}

resource "aws_sagemaker_model" "vllm" {
  name               = local.resource_name
  execution_role_arn = aws_iam_role.sagemaker_execution.arn

  primary_container {
    image = local.image_uri

    environment = {
      HF_MODEL_ID                   = var.model_id
      OPTION_MODEL_ID               = var.model_id
      OPTION_TASK                   = "text-generation"
      OPTION_ENGINE                 = "Python"
      OPTION_ROLLING_BATCH          = "vllm"
      OPTION_DTYPE                  = "auto"
      OPTION_TENSOR_PARALLEL_DEGREE = "max"
      OPTION_MAX_MODEL_LEN          = tostring(var.max_model_len)
      OPTION_GPU_MEMORY_UTILIZATION = tostring(var.gpu_memory_utilization)
      OPTION_TRUST_REMOTE_CODE      = tostring(var.trust_remote_code)
      HUGGING_FACE_HUB_TOKEN        = var.hugging_face_hub_token
      HF_TOKEN                      = var.hugging_face_hub_token
    }
  }

  depends_on = [time_sleep.iam_propagation]
}

resource "aws_sagemaker_endpoint_configuration" "vllm" {
  name = local.resource_name

  production_variants {
    variant_name                                      = "AllTraffic"
    model_name                                        = aws_sagemaker_model.vllm.name
    initial_instance_count                            = var.initial_instance_count
    instance_type                                     = var.instance_type
    initial_variant_weight                            = 1
    container_startup_health_check_timeout_in_seconds = 3600
    model_data_download_timeout_in_seconds            = 3600
  }

  depends_on = [time_sleep.iam_propagation]
}

resource "aws_sagemaker_endpoint" "vllm" {
  name                 = local.resource_name
  endpoint_config_name = aws_sagemaker_endpoint_configuration.vllm.name
}
