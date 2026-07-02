#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_DIR="${ROOT}/deploy/sagemaker-vllm"

export AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-2}}"
export SAGEMAKER_ADAPTER_API_KEY="${SAGEMAKER_ADAPTER_API_KEY:-sk-sagemaker-adapter}"

if [[ -z "${SAGEMAKER_ENDPOINT_NAME:-}" ]]; then
  SAGEMAKER_ENDPOINT_NAME="$(terraform -chdir="${TF_DIR}" output -raw endpoint_name)"
  export SAGEMAKER_ENDPOINT_NAME
fi

exec python3 "${ROOT}/scripts/sagemaker_openai_adapter.py" \
  --endpoint-name "${SAGEMAKER_ENDPOINT_NAME}" \
  --region "${AWS_REGION}" \
  --model coding-local
