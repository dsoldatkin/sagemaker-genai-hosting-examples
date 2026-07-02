#!/usr/bin/env python3
"""End-to-end smoke test for the deployed coder harness gateway."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TF_DIR = ROOT / "deploy" / "aws-g6e"


def terraform_output() -> dict:
    # subprocess with static command list - safe; TF_DIR is derived from known path
    if not TF_DIR.is_dir():
        raise RuntimeError(f"Terraform directory not found: {TF_DIR}")
    raw = subprocess.check_output(
        ["terraform", "output", "-json"],
        cwd=str(TF_DIR),
        text=True,
    )
    return json.loads(raw)


def request_json(url: str, api_key: str, payload: dict | None = None) -> dict:
    # Validate URL scheme to prevent file:/ or other unexpected protocols
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"Only http:// and https:// schemes are supported, got: {url}")
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Authorization": f"Bearer {api_key}"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method="GET" if body is None else "POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    outputs = terraform_output()
    base_url = os.environ.get("BASE_URL") or outputs["gateway_base_url"]["value"]
    api_key = os.environ.get("API_KEY") or outputs["litellm_api_key"]["value"]
    model = os.environ.get("MODEL", "coding-default")

    deadline = time.time() + int(os.environ.get("WAIT_SECONDS", "3600"))
    last_error = None

    while time.time() < deadline:
        try:
            models = request_json(f"{base_url}/models", api_key)
            if "data" in models:
                break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
        time.sleep(20)
    else:
        print(f"Gateway did not become ready: {last_error}", file=sys.stderr)
        return 1

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a concise coding assistant."},
            {
                "role": "user",
                "content": "Write a Python function named square that returns n * n. Return only code.",
            },
        ],
        "max_tokens": 128,
        "temperature": 0,
    }
    response = request_json(f"{base_url}/chat/completions", api_key, payload)
    content = response["choices"][0]["message"]["content"]

    if "def square" not in content or "n" not in content:
        print("Unexpected completion:", file=sys.stderr)
        print(content, file=sys.stderr)
        return 1

    # NOTE: This is test-only code. In production, use structured logging with
    # explicit field selection (e.g., request_id, status, token_count) rather
    # than printing full response content.
    print(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
