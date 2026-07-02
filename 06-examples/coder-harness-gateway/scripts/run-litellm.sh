#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="${CONFIG_PATH:-config/litellm/config.example.yaml}"
PORT="${PORT:-4000}"

if [[ -z "${LITELLM_MASTER_KEY:-}" ]]; then
  echo "Set LITELLM_MASTER_KEY before starting the gateway" >&2
  exit 1
fi

litellm --config "${CONFIG_PATH}" --port "${PORT}"
