#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_PATH="${CONFIG_PATH:-${ROOT}/config/litellm/sagemaker-bedrock.config.yaml}"
PORT="${PORT:-4000}"

export AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-2}}"
export LITELLM_MASTER_KEY="${LITELLM_MASTER_KEY:-sk-local-litellm}"
export SAGEMAKER_ADAPTER_API_KEY="${SAGEMAKER_ADAPTER_API_KEY:-sk-sagemaker-adapter}"

exec litellm --config "${CONFIG_PATH}" --host 127.0.0.1 --port="${PORT}"
