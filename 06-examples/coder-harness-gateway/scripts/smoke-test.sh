#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:4000/v1}"
API_KEY="${API_KEY:-${LITELLM_API_KEY:-}}"
MODEL="${MODEL:-coding-default}"

if [[ -z "${API_KEY}" ]]; then
  echo "Set API_KEY or LITELLM_API_KEY" >&2
  exit 1
fi

curl -fsS "${BASE_URL}/models" \
  -H "Authorization: Bearer ${API_KEY}" \
  >/dev/null

curl -fsS "${BASE_URL}/chat/completions" \
  -H "Authorization: Bearer ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"${MODEL}\",
    \"messages\": [
      {\"role\": \"system\", \"content\": \"You are a concise coding assistant.\"},
      {\"role\": \"user\", \"content\": \"Write a Python function that returns the square of an integer.\"}
    ],
    \"max_tokens\": 128
  }"
