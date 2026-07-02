#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${ROOT}/tests/lib_gateway.sh"

command -v claude >/dev/null

start_gateway_stack

OUT="$(
  curl -fsS http://127.0.0.1:4000/v1/messages \
    -H "x-api-key: ${LITELLM_API_KEY}" \
    -H "Authorization: Bearer ${LITELLM_API_KEY}" \
    -H "anthropic-version: 2023-06-01" \
    -H "content-type: application/json" \
    -d '{
      "model": "coding-default",
      "max_tokens": 32,
      "messages": [
        {"role": "user", "content": "Reply exactly CLAUDE_LITELLM_OK."}
      ]
    }'
)"

printf '%s\n' "${OUT}"
grep -q "CLAUDE_LITELLM_OK" <<<"${OUT}"

if [[ "${RUN_CLAUDE_CLI_TEST:-0}" == "1" ]]; then
  CLI_OUT="$(
    CLAUDE_CODE_API_BASE_URL="http://127.0.0.1:4000" \
    BASE_API_URL="http://127.0.0.1:4000" \
    ANTHROPIC_BASE_URL="http://127.0.0.1:4000" \
    _CLAUDE_CODE_ASSUME_FIRST_PARTY_BASE_URL="1" \
    ANTHROPIC_API_KEY="${LITELLM_API_KEY}" \
    claude --bare -p \
      --model coding-default \
      --output-format text \
      "Reply exactly CLAUDE_LITELLM_OK. Do not use tools."
  )"
  printf '%s\n' "${CLI_OUT}"
  grep -q "CLAUDE_LITELLM_OK" <<<"${CLI_OUT}"
fi
