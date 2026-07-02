# Spec: Coder Harness Gateway

## Overview

Build a local-first model gateway for coding harnesses. Codex and Claude Code should connect natively through their preferred API contracts, while the gateway routes requests to either a self-hosted vLLM endpoint on SageMaker or Bedrock-hosted fallback models.

## Goals

- Provide one stable internal endpoint for coding harnesses.
- Support OpenAI-compatible clients, including Codex.
- Support Anthropic Messages-compatible clients, including Claude Code.
- Serve a strong self-hosted coder model on SageMaker with vLLM.
- Combine local vLLM models with Bedrock models behind model aliases.
- Add routing, fallback, auth, logging, and policy centrally.

## Primary User Flows

1. A developer starts Codex in a repo and selects `coding-default`.
2. Codex sends OpenAI-compatible requests to the gateway.
3. The gateway routes to `coding-local` on vLLM by default.
4. If local serving is unavailable or a policy requires stronger reasoning, the gateway falls back to `coding-strong` on Bedrock.
5. A developer starts Claude Code with an Anthropic-compatible base URL.
6. Claude Code sends Messages API requests to the gateway.
7. The gateway translates or routes the request to the selected backend.

## Recommended Model Plan

### Phase 1: Single-GPU Local Baseline

Default model:

- `Qwen2.5-Coder-32B-Instruct` using AWQ, GPTQ, or FP8 if available and validated.

Preferred hardware:

- SageMaker `ml.g6e.2xlarge` once endpoint quota is available.
- SageMaker `ml.g5.12xlarge` as the tested deployable fallback in this account.
- Prefer enough aggregate GPU memory and host memory to avoid slow cold starts.

Serving:

- vLLM OpenAI-compatible server.
- Conservative context length first, then increase after latency and memory validation.

Initial vLLM settings:

```text
--served-model-name coding-local
--max-model-len 32768
--gpu-memory-utilization 0.90
--enable-auto-tool-choice
--tool-call-parser hermes
```

Notes:

- If tool calling is unreliable for the selected checkpoint, keep tool execution in the harness and use the model for reasoning and patch generation only.
- If latency is too high, add `Qwen2.5-Coder-14B-Instruct` as `coding-fast`.
- If quality is insufficient, keep G6e for private/local work and route difficult tasks to Bedrock as `coding-strong`.

### Phase 2: Bedrock Strong Route

Add a Bedrock-hosted model as `coding-strong`.

Use cases:

- difficult repo-wide reasoning
- long-context review
- failure recovery when the local model loops
- premium route for high-value tasks

The exact Bedrock model ID should remain config-driven because model availability varies by region and account.

## Gateway Contract

Expose:

- OpenAI-compatible `/v1/chat/completions`.
- OpenAI-compatible `/v1/models`.
- Anthropic-compatible `/v1/messages` when supported by the gateway.

Model aliases:

| Alias | Backend | Purpose |
| --- | --- | --- |
| `coding-default` | router | Default harness model |
| `coding-local` | vLLM | Private/local coding assistant |
| `coding-fast` | vLLM | Low-latency coding route |
| `coding-strong` | Bedrock | Premium fallback route |

Required gateway behavior:

- Authenticate all clients with a gateway key.
- Hide provider credentials from clients.
- Log request ID, user, harness, model alias, backend model, latency, tokens, status, and fallback reason.
- Support per-user and per-harness model allowlists.
- Cap max input and output tokens per alias.
- Disable prompt logging by default unless explicitly enabled for an isolated environment.

## Codex Integration

Codex should use a custom model provider in user-level `~/.codex/config.toml`.

Use `wire_api = "chat"` for the first version because vLLM and LiteLLM OpenAI-compatible chat routes are the lowest-friction path.

Move to `wire_api = "responses"` only after the gateway has a verified Responses-compatible path.

## Claude Code Integration

Claude Code should connect to an Anthropic-compatible gateway endpoint. Keep Claude Code on its native Messages API shape and let the gateway translate to vLLM or Bedrock.

Expected environment variables are captured in `clients/claude-code/env.example`. Verify the exact variable names against the installed Claude Code version before rollout.

## Security Requirements

- Gateway keys are separate from Bedrock, AWS, and vLLM credentials.
- Bedrock credentials stay only on the gateway host or in its runtime identity.
- vLLM is reachable only from the gateway security group or private network.
- Client traffic uses TLS outside localhost.
- Logs redact prompts by default.
- Gateway admin endpoints are not exposed publicly.

## Observability Requirements

Record:

- request ID
- client/harness name
- user identity or key alias
- requested model alias
- selected backend
- status code
- latency
- prompt tokens
- completion tokens
- fallback reason
- error class

Minimum dashboards:

- p50/p95 latency by alias and backend
- error rate by alias and backend
- token volume by user and harness
- fallback rate
- vLLM GPU memory and utilization

## Success Criteria

- Codex can complete a simple code edit through `coding-default`.
- Claude Code can complete a simple code edit through `coding-default`.
- Gateway can route to vLLM by default.
- Gateway can route to Bedrock through `coding-strong`.
- A local vLLM outage triggers the configured fallback.
- Smoke tests validate `/v1/models` and one chat completion.
- No client needs direct vLLM or Bedrock credentials.

## Non-Requirements

- No custom harness fork.
- No multi-tenant billing system in the first version.
- No fine-tuning pipeline in the first version.
- No custom model router until baseline metrics exist.
- No persistent conversation memory in the gateway.

## Open Decisions

- Exact G6e size.
- Exact quantized checkpoint artifact.
- Whether the gateway will expose Anthropic Messages directly through LiteLLM or through a small compatibility sidecar.
- Bedrock model ID and region for `coding-strong`.
- Whether prompt logging is allowed in any development environment.
