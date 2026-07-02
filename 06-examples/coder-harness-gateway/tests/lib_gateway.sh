#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-2}}"
export LITELLM_MASTER_KEY="${LITELLM_MASTER_KEY:-sk-local-litellm}"
export LITELLM_API_KEY="${LITELLM_API_KEY:-${LITELLM_MASTER_KEY}}"
export SAGEMAKER_ADAPTER_API_KEY="${SAGEMAKER_ADAPTER_API_KEY:-sk-sagemaker-adapter}"

wait_for_url() {
  local url="$1"
  local header="$2"
  local deadline=$((SECONDS + ${WAIT_SECONDS:-180}))
  until curl -fsS ${header:+-H "$header"} "$url" >/dev/null 2>&1; do
    if (( SECONDS > deadline )); then
      echo "Timed out waiting for $url" >&2
      return 1
    fi
    sleep 2
  done
}

start_gateway_stack() {
  if [[ -z "${SAGEMAKER_ENDPOINT_NAME:-}" ]]; then
    SAGEMAKER_ENDPOINT_NAME="$(terraform -chdir="${ROOT}/deploy/sagemaker-vllm" output -raw endpoint_name)"
    export SAGEMAKER_ENDPOINT_NAME
  fi

  "${ROOT}/scripts/run-sagemaker-openai-adapter.sh" >"${ROOT}/.adapter.log" 2>&1 &
  ADAPTER_PID=$!
  "${ROOT}/scripts/run-litellm-sagemaker-bedrock.sh" >"${ROOT}/.litellm.log" 2>&1 &
  LITELLM_PID=$!

  trap stop_gateway_stack EXIT

  wait_for_url "http://127.0.0.1:8088/v1/models" "Authorization: Bearer ${SAGEMAKER_ADAPTER_API_KEY}"
  wait_for_url "http://127.0.0.1:4000/v1/models" "Authorization: Bearer ${LITELLM_API_KEY}"
}

stop_gateway_stack() {
  if [[ -n "${LITELLM_PID:-}" ]]; then
    kill "${LITELLM_PID}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${ADAPTER_PID:-}" ]]; then
    kill "${ADAPTER_PID}" >/dev/null 2>&1 || true
  fi
}
