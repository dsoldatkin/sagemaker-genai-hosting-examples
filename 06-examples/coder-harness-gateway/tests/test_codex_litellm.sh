#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${ROOT}/tests/lib_gateway.sh"

command -v codex >/dev/null

start_gateway_stack

TMP_CODEX_HOME="$(mktemp -d)"
OUT_FILE="$(mktemp)"
cp "${ROOT}/clients/codex/litellm-sagemaker-bedrock.config.toml" "${TMP_CODEX_HOME}/config.toml"

CODEX_HOME="${TMP_CODEX_HOME}" \
LITELLM_API_KEY="${LITELLM_API_KEY}" \
codex exec \
  --skip-git-repo-check \
  --sandbox read-only \
  --output-last-message "${OUT_FILE}" \
  "Reply exactly CODEX_LITELLM_OK. Do not run tools."

cat "${OUT_FILE}"
grep -q "CODEX_LITELLM_OK" "${OUT_FILE}"
