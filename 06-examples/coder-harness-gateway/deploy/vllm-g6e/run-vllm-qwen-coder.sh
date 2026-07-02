#!/usr/bin/env bash
set -euo pipefail

# Baseline vLLM launch for a single-GPU G6e endpoint.
# Set MODEL_ID to the exact quantized checkpoint you validate.

MODEL_ID="${MODEL_ID:-Qwen/Qwen2.5-Coder-32B-Instruct-AWQ}"
SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-coding-local}"
PORT="${PORT:-8000}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-32768}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.90}"

python -m vllm.entrypoints.openai.api_server \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --model "${MODEL_ID}" \
  --served-model-name "${SERVED_MODEL_NAME}" \
  --max-model-len "${MAX_MODEL_LEN}" \
  --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}" \
  --enable-auto-tool-choice \
  --tool-call-parser hermes
