data "aws_vpc" "selected" {
  default = var.vpc_id == null ? true : null
  id      = var.vpc_id
}

data "aws_subnets" "selected" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.selected.id]
  }
}

data "aws_ami" "dlami" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 22.04) *"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }

  filter {
    name   = "root-device-type"
    values = ["ebs"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "random_password" "litellm_master_key" {
  length  = 32
  special = false
}

locals {
  subnet_id          = coalesce(var.subnet_id, sort(data.aws_subnets.selected.ids)[0])
  litellm_master_key = coalesce(var.litellm_master_key, random_password.litellm_master_key.result)
  gateway_port       = 4000
  vllm_port          = 8000
}

resource "aws_security_group" "endpoint" {
  name        = "${var.name_prefix}-sg"
  description = "Coder harness gateway access"
  vpc_id      = data.aws_vpc.selected.id

  ingress {
    description = "LiteLLM gateway"
    from_port   = local.gateway_port
    to_port     = local.gateway_port
    protocol    = "tcp"
    cidr_blocks = [var.allowed_cidr]
  }

  ingress {
    description = "Direct vLLM OpenAI API for diagnostics"
    from_port   = local.vllm_port
    to_port     = local.vllm_port
    protocol    = "tcp"
    cidr_blocks = [var.allowed_cidr]
  }

  egress {
    description = "Outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.name_prefix}-sg"
  }
}

resource "aws_iam_role" "instance" {
  name = "${var.name_prefix}-instance-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "instance" {
  name = "${var.name_prefix}-instance-profile"
  role = aws_iam_role.instance.name
}

resource "aws_instance" "endpoint" {
  ami                         = data.aws_ami.dlami.id
  instance_type               = var.instance_type
  subnet_id                   = local.subnet_id
  vpc_security_group_ids      = [aws_security_group.endpoint.id]
  iam_instance_profile        = aws_iam_instance_profile.instance.name
  associate_public_ip_address = var.associate_public_ip

  root_block_device {
    volume_size = var.root_volume_size_gb
    volume_type = "gp3"
    throughput  = 250
    iops        = 6000
  }

  user_data_replace_on_change = true
  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    model_id               = var.model_id
    served_model_name      = var.served_model_name
    max_model_len          = var.max_model_len
    gpu_memory_utilization = var.gpu_memory_utilization
    vllm_image             = var.vllm_image
    litellm_image          = var.litellm_image
    hugging_face_hub_token = var.hugging_face_hub_token
    litellm_master_key     = local.litellm_master_key
    gateway_port           = local.gateway_port
    vllm_port              = local.vllm_port
  })

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  tags = {
    Name = "${var.name_prefix}-g6e"
  }
}
