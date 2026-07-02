#!/usr/bin/env python3
"""End-to-end smoke test for the SageMaker vLLM endpoint."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError


ROOT = Path(__file__).resolve().parents[1]
TF_DIR = ROOT / "deploy" / "sagemaker-vllm"


def terraform_output() -> dict[str, Any]:
    # subprocess with static command list - safe; TF_DIR is derived from known path
    if not TF_DIR.is_dir():
        raise RuntimeError(f"Terraform directory not found: {TF_DIR}")
    raw = subprocess.check_output(["terraform", "output", "-json"], cwd=str(TF_DIR), text=True)
    return json.loads(raw)


def decode_response(raw: bytes) -> str:
    payload = json.loads(raw.decode("utf-8"))
    if isinstance(payload, list) and payload:
        first = payload[0]
        if isinstance(first, dict):
            return str(first.get("generated_text") or first.get("text") or first)
        return str(first)
    if isinstance(payload, dict):
        if "generated_text" in payload:
            return str(payload["generated_text"])
        if "outputs" in payload:
            return str(payload["outputs"])
        if "choices" in payload:
            return str(payload["choices"][0]["message"]["content"])
    return str(payload)


def main() -> int:
    outputs = terraform_output()
    endpoint_name = os.environ.get("ENDPOINT_NAME") or outputs["endpoint_name"]["value"]
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or outputs["region"]["value"]

    sm = boto3.client("sagemaker", region_name=region)
    runtime = boto3.client("sagemaker-runtime", region_name=region)

    waiter = sm.get_waiter("endpoint_in_service")
    print(f"Waiting for SageMaker endpoint {endpoint_name} in {region}...")
    try:
        waiter.wait(
            EndpointName=endpoint_name,
            WaiterConfig={"Delay": 60, "MaxAttempts": int(os.environ.get("WAITER_MAX_ATTEMPTS", "90"))},
        )
    except ClientError as exc:
        print(f"Endpoint did not reach InService: {exc}", file=sys.stderr)
        return 1

    body = {
        "inputs": "Write a Python function named square that returns n * n. Return only code.",
        "parameters": {
            "max_new_tokens": 128,
            "temperature": 0.0,
        },
    }
    response = runtime.invoke_endpoint(
        EndpointName=endpoint_name,
        ContentType="application/json",
        Accept="application/json",
        Body=json.dumps(body).encode("utf-8"),
    )
    text = decode_response(response["Body"].read())

    if "def square" not in text or "n" not in text:
        print("Unexpected completion:", file=sys.stderr)
        print(text, file=sys.stderr)
        return 1

    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
