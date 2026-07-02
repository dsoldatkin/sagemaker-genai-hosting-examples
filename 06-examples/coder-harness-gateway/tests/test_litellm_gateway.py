#!/usr/bin/env python3
"""Smoke test LiteLLM routing to local SageMaker/vLLM and optional Bedrock aliases."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def wait_models(api_key: str, deadline: float) -> None:
    while time.time() < deadline:
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:4000/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                json.loads(resp.read().decode("utf-8"))
                return
        except Exception:
            time.sleep(2)
    raise TimeoutError("LiteLLM /v1/models did not become ready")


def completion(model: str, api_key: str, expected: str) -> str:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": f"Reply exactly {expected}."}],
        "max_tokens": 128,
        "temperature": 0,
    }
    req = urllib.request.Request(
        "http://127.0.0.1:4000/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body["choices"][0]["message"].get("content") or ""


def completion_with_retry(model: str, api_key: str, expected: str) -> str:
    last = ""
    for _ in range(3):
        last = completion(model, api_key, expected)
        if expected in last:
            return last
        time.sleep(2)
    return last


def main() -> int:
    env = os.environ.copy()
    env.setdefault("AWS_REGION", env.get("AWS_DEFAULT_REGION", "us-east-2"))
    env.setdefault("LITELLM_MASTER_KEY", "sk-local-litellm")
    env.setdefault("LITELLM_API_KEY", env["LITELLM_MASTER_KEY"])
    env.setdefault("SAGEMAKER_ADAPTER_API_KEY", "sk-sagemaker-adapter")
    if "SAGEMAKER_ENDPOINT_NAME" not in env:
        env["SAGEMAKER_ENDPOINT_NAME"] = subprocess.check_output(
            ["terraform", "-chdir=deploy/sagemaker-vllm", "output", "-raw", "endpoint_name"],
            cwd=ROOT,
            text=True,
        ).strip()

    adapter = subprocess.Popen([str(ROOT / "scripts" / "run-sagemaker-openai-adapter.sh")], cwd=ROOT, env=env)
    gateway = subprocess.Popen([str(ROOT / "scripts" / "run-litellm-sagemaker-bedrock.sh")], cwd=ROOT, env=env)
    try:
        wait_models(env["LITELLM_API_KEY"], time.time() + int(env.get("WAIT_SECONDS", "180")))
        models = {"coding-default": "LITELLM_OK"}
        if env.get("RUN_BEDROCK_TESTS") == "1":
            models.update({"coding-gpt": "GPT_OK", "coding-opus": "OPUS_OK"})
        for model, expected in models.items():
            text = completion_with_retry(model, env["LITELLM_API_KEY"], expected)
            print(f"{model}: {text}")
            if expected not in text:
                raise AssertionError(f"{model} did not return {expected!r}")
        return 0
    finally:
        gateway.terminate()
        adapter.terminate()
        gateway.wait(timeout=10)
        adapter.wait(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
