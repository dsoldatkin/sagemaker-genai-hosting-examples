# Design Decisions

## Use a Gateway Instead of Direct Harness Integrations

Decision: Codex and Claude Code connect to a gateway, not directly to vLLM or Bedrock.

Reasoning:

- Codex and Claude Code have different native API expectations.
- vLLM and Bedrock have different auth, model IDs, and feature support.
- Central routing lets us add fallback, observability, policy, and model aliases once.

## Start with OpenAI Chat for Codex

Decision: Use Codex `wire_api = "chat"` for the first gateway integration.

Reasoning:

- vLLM's OpenAI-compatible chat endpoint is mature and easy to test.
- LiteLLM commonly fronts OpenAI-compatible chat routes.
- OpenAI Responses compatibility can be added later after it is verified end to end.

## Keep Claude Code Messages-Native

Decision: Claude Code should use an Anthropic-compatible Messages endpoint.

Reasoning:

- It avoids client-side translation.
- Claude Code behavior is more likely to remain stable when using its native API shape.
- The gateway is the right place to translate Messages requests to backend-specific calls.

## Use Qwen2.5-Coder-32B as the First Local Model

Decision: Use a quantized `Qwen2.5-Coder-32B-Instruct` checkpoint as `coding-local`.

Reasoning:

- It is a strong open coding model with broad deployment support.
- It is realistic on a single G6e GPU when quantized.
- It is a better first operational target than a larger MoE model that requires more complex tensor/expert parallelism.

## Keep Bedrock as a Strong Route

Decision: Use Bedrock for `coding-strong`, not as the only route.

Reasoning:

- Bedrock gives a managed high-quality fallback.
- Local vLLM preserves privacy, cost control, and low-latency iteration for normal coding tasks.
- Routing can evolve from static fallback to policy-based selection after telemetry exists.
