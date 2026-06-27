# Deploy GLM-5.2-FP8 on Amazon SageMaker AI

This example demonstrates how to deploy [GLM-5.2-FP8](https://huggingface.co/zai-org/GLM-5.2-FP8) on an Amazon SageMaker AI real-time endpoint using `boto3` (no SageMaker Python SDK dependency).

## Model

GLM-5.2 is Z.ai's flagship open-weights model, built for long-horizon coding and agentic work. `GLM-5.2-FP8` is the FP8-quantized release, published under an MIT license.

| Property | Value |
| :--- | :--- |
| Model | [`zai-org/GLM-5.2-FP8`](https://huggingface.co/zai-org/GLM-5.2-FP8) |
| Architecture | Mixture-of-Experts (MoE), ~744B total / ~40B active per token |
| Context window | Up to 1M tokens (notebook configures 65,535) |
| Quantization | FP8 |
| License | MIT |

### Key Architecture Highlights

- **Sparse attention with IndexShare** — reuses one indexer across every four sparse-attention layers, cutting per-token FLOPs by about 2.9x at 1M context.
- **Improved MTP layer** — lifts speculative-decoding acceptance length by up to 20%.
- **Flexible thinking effort** — multiple reasoning-effort levels to balance response quality against latency.

Learn more in the [GLM-5.2 blog](https://z.ai/blog/glm-5.2). Architecture and benchmark details are quoted from the published Hugging Face model card.

## Serving Frameworks

The notebook provides two deployment options using AWS Deep Learning Containers (DLCs) — pick **one**:

| Option | Container | Version |
| :--- | :--- | :--- |
| vLLM | SageMaker [vLLM DLC](https://aws.github.io/deep-learning-containers/vllm/) | 0.23.0 |
| SGLang | SageMaker [SGLang DLC](https://aws.github.io/deep-learning-containers/sglang/) | 0.5.13 |

Both containers run an OpenAI-compatible API server. The SGLang option additionally configures EAGLE speculative decoding.

## Instance Requirements

- **Instance type:** `ml.p5en.48xlarge` (8 GPUs)
- **Inference AMI:** `al2023-ami-sagemaker-inference-gpu-4-1`
- Capacity reservation is supported via the endpoint configuration (optional, recommended for availability).

## Key Configuration

| Setting | Value |
| :--- | :--- |
| Instance | `ml.p5en.48xlarge` (8 GPUs) |
| Tensor Parallel | 8 |
| Max Context Length | 65,535 tokens |
| KV Cache (vLLM) | FP8 |
| Tool Calling (vLLM) | Enabled (`glm47` parser) |
| Reasoning (vLLM) | Enabled (`glm45` parser) |
| Speculative Decoding (SGLang) | EAGLE |

## Notebook Contents

| Section | Description |
| :--- | :--- |
| Container | Set the instance, model ID, and endpoint names |
| Deployment options | Choose and configure the vLLM or SGLang container |
| Deployment | Create the SageMaker Model, Endpoint Configuration, and Endpoint |
| Text inference | Basic text generation |
| Text generation, no reasoning | Generation with thinking disabled |
| Text inference with reasoning | Generation with `reasoning_effort` enabled |
| Cleanup | Delete the endpoint, endpoint config, and model |

## Getting Started

1. Open the notebook in SageMaker Studio or a Jupyter environment with appropriate AWS credentials.
2. Install dependencies (`boto3`).
3. Set your Hugging Face token (`HF_TOKEN`) in the container environment variables cell.
4. Choose one serving framework (vLLM or SGLang) and run **only** that cell.
5. Run the deployment cells and wait for the endpoint to reach `InService`.
6. Run the inference examples.
7. Run the cleanup cell when done to avoid ongoing charges.

## Prerequisites

- AWS account with access to `ml.p5en.48xlarge` instances (capacity reservation recommended for availability).
- IAM role with SageMaker execution permissions (create models, endpoints, and pull ECR images).
- Hugging Face access token is recommended.
