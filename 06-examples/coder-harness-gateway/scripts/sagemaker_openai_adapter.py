#!/usr/bin/env python3
"""OpenAI-compatible adapter for the SageMaker DJL/vLLM endpoint.

LiteLLM can front this adapter as an OpenAI-compatible backend. The adapter
keeps SageMaker's DJL text-generation payload isolated from harness configs.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import boto3


def chat_prompt(messages: list[dict[str, str]]) -> str:
    rendered = []
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")
        if isinstance(content, list):
            content = "\n".join(str(part.get("text", part)) for part in content)
        rendered.append(f"<|im_start|>{role}\n{content}<|im_end|>")
    rendered.append("<|im_start|>assistant\n")
    return "\n".join(rendered)


def responses_prompt(input_value: Any) -> str:
    if isinstance(input_value, str):
        return input_value
    if isinstance(input_value, list):
        messages: list[dict[str, str]] = []
        for item in input_value:
            if not isinstance(item, dict):
                continue
            role = item.get("role", "user")
            content = item.get("content", "")
            if isinstance(content, list):
                parts = []
                for part in content:
                    if isinstance(part, dict):
                        parts.append(str(part.get("text") or part.get("input_text") or part))
                    else:
                        parts.append(str(part))
                content = "\n".join(parts)
            messages.append({"role": role, "content": str(content)})
        return chat_prompt(messages)
    return str(input_value)


def extract_text(payload: Any) -> str:
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


class Handler(BaseHTTPRequestHandler):
    server_version = "SageMakerOpenAIAdapter/0.1"

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _check_auth(self) -> bool:
        expected = os.environ.get("SAGEMAKER_ADAPTER_API_KEY", "")
        if not expected:
            # Fail closed: reject all requests when API key is not configured
            return False
        auth = self.headers.get("Authorization", "")
        return auth == f"Bearer {expected}"

    def do_GET(self) -> None:  # noqa: N802
        if not self._check_auth():
            self._json(401, {"error": {"message": "unauthorized"}})
            return
        if self.path in {"/health", "/v1/health"}:
            self._json(200, {"status": "ok"})
            return
        if self.path == "/v1/models":
            model = os.environ["SAGEMAKER_ADAPTER_MODEL"]
            self._json(
                200,
                {
                    "object": "list",
                    "data": [
                        {
                            "id": model,
                            "object": "model",
                            "created": 0,
                            "owned_by": "sagemaker",
                        }
                    ],
                },
            )
            return
        self._json(404, {"error": {"message": "not found"}})

    def do_POST(self) -> None:  # noqa: N802
        if not self._check_auth():
            self._json(401, {"error": {"message": "unauthorized"}})
            return
        if self.path == "/v1/chat/completions":
            self._chat_completions()
            return
        if self.path == "/v1/responses":
            self._responses()
            return
        self._json(404, {"error": {"message": "not found"}})

    def _invoke_sagemaker(self, prompt: str, max_tokens: int, temperature: float) -> str:
        body = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": max_tokens,
                "temperature": temperature,
            },
        }
        runtime = self.server.runtime  # type: ignore[attr-defined]
        result = runtime.invoke_endpoint(
            EndpointName=os.environ["SAGEMAKER_ENDPOINT_NAME"],
            ContentType="application/json",
            Accept="application/json",
            Body=json.dumps(body).encode("utf-8"),
        )
        generated = extract_text(json.loads(result["Body"].read().decode("utf-8")))
        if "<|im_start|>assistant" in generated:
            generated = generated.split("<|im_start|>assistant", 1)[-1]
        return generated.replace("<|im_end|>", "").strip()

    def _chat_completions(self) -> None:
        request = self._read_json()
        model = request.get("model") or os.environ["SAGEMAKER_ADAPTER_MODEL"]
        prompt = chat_prompt(request.get("messages", []))
        max_tokens = int(request.get("max_tokens") or request.get("max_completion_tokens") or 512)
        temperature = float(request.get("temperature", 0.0) or 0.0)
        generated = self._invoke_sagemaker(prompt, max_tokens, temperature)

        created = int(time.time())
        response_id = f"chatcmpl-{uuid.uuid4().hex}"
        if request.get("stream"):
            chunk = {
                "id": response_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {"content": generated}, "finish_reason": None}],
            }
            done = {
                "id": response_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode("utf-8"))
            self.wfile.write(f"data: {json.dumps(done)}\n\n".encode("utf-8"))
            self.wfile.write(b"data: [DONE]\n\n")
            return

        self._json(
            200,
            {
                "id": response_id,
                "object": "chat.completion",
                "created": created,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": generated},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
            },
        )

    def _responses(self) -> None:
        request = self._read_json()
        model = request.get("model") or os.environ["SAGEMAKER_ADAPTER_MODEL"]
        prompt = responses_prompt(request.get("input", ""))
        max_tokens = int(request.get("max_output_tokens") or request.get("max_tokens") or 512)
        temperature = float(request.get("temperature", 0.0) or 0.0)
        generated = self._invoke_sagemaker(prompt, max_tokens, temperature)
        created = int(time.time())
        response_id = f"resp_{uuid.uuid4().hex}"
        item_id = f"msg_{uuid.uuid4().hex}"
        content = {
            "type": "output_text",
            "text": generated,
            "annotations": [],
        }
        output_item = {
            "id": item_id,
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": [content],
        }
        response = {
            "id": response_id,
            "object": "response",
            "created_at": created,
            "status": "completed",
            "model": model,
            "output": [output_item],
            "parallel_tool_calls": True,
            "tool_choice": "auto",
            "tools": [],
            "usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            },
        }
        if request.get("stream"):
            events = [
                {"type": "response.created", "response": {**response, "status": "in_progress", "output": []}},
                {"type": "response.output_item.added", "output_index": 0, "item": {**output_item, "content": []}},
                {"type": "response.content_part.added", "item_id": item_id, "output_index": 0, "content_index": 0, "part": {**content, "text": ""}},
                {"type": "response.output_text.delta", "item_id": item_id, "output_index": 0, "content_index": 0, "delta": generated},
                {"type": "response.output_text.done", "item_id": item_id, "output_index": 0, "content_index": 0, "text": generated},
                {"type": "response.content_part.done", "item_id": item_id, "output_index": 0, "content_index": 0, "part": content},
                {"type": "response.output_item.done", "output_index": 0, "item": output_item},
                {"type": "response.completed", "response": response},
            ]
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for event in events:
                self.wfile.write(f"event: {event['type']}\n".encode("utf-8"))
                self.wfile.write(f"data: {json.dumps(event)}\n\n".encode("utf-8"))
            return

        self._json(200, response)

    def log_message(self, fmt: str, *args: Any) -> None:
        # WARNING: Debug logging may expose sensitive request/response data.
        # ADAPTER_DEBUG must NEVER be enabled in production environments.
        # When debug logging is needed, prefer structured logging with explicit
        # field selection to exclude sensitive data.
        if os.environ.get("ADAPTER_DEBUG") == "1":
            super().log_message(fmt, *args)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8088)
    parser.add_argument("--endpoint-name", default=os.environ.get("SAGEMAKER_ENDPOINT_NAME"))
    parser.add_argument("--region", default=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-2")
    parser.add_argument("--model", default=os.environ.get("SAGEMAKER_ADAPTER_MODEL", "coding-local"))
    args = parser.parse_args()

    if not args.endpoint_name:
        raise SystemExit("Set SAGEMAKER_ENDPOINT_NAME or pass --endpoint-name")

    if not os.environ.get("SAGEMAKER_ADAPTER_API_KEY"):
        raise SystemExit(
            "SAGEMAKER_ADAPTER_API_KEY environment variable must be set. "
            "The adapter will reject all requests without a configured API key."
        )

    os.environ["SAGEMAKER_ENDPOINT_NAME"] = args.endpoint_name
    os.environ["SAGEMAKER_ADAPTER_MODEL"] = args.model

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.runtime = boto3.client("sagemaker-runtime", region_name=args.region)  # type: ignore[attr-defined]
    print(f"SageMaker OpenAI adapter listening on http://{args.host}:{args.port}/v1")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
