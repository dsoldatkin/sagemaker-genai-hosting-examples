# Harness Orchestration

The harnesses should not know provider-specific model IDs. They select stable gateway aliases:

| Alias | Backend | Role |
| --- | --- | --- |
| `coding-default` | LiteLLM router | Normal Codex/Claude Code model |
| `coding-local` | SageMaker vLLM | Private/local coding baseline |
| `coding-gpt` | Bedrock OpenAI | GPT fallback and cross-check |
| `coding-opus` | Bedrock Claude Opus | Strong fallback |
| `coding-strong` | Bedrock Claude Opus | Explicit premium route |

Current Bedrock IDs generated from this account/region:

```text
openai.gpt-oss-120b-1:0
us.anthropic.claude-opus-4-5-20251101-v1:0
```

LiteLLM config:

```text
config/litellm/sagemaker-bedrock.config.yaml
```

Routing behavior:

- `coding-default` starts with SageMaker/vLLM.
- If `coding-default` fails, LiteLLM falls back to `coding-gpt`.
- If `coding-gpt` fails, LiteLLM falls back to `coding-opus`.
- Harnesses can explicitly request `coding-gpt` or `coding-opus` for comparison runs.

Run the local gateway stack:

```bash
./scripts/run-sagemaker-openai-adapter.sh
./scripts/run-litellm-sagemaker-bedrock.sh
```

Run tests:

```bash
./tests/test_litellm_gateway.py
./tests/test_codex_litellm.sh
./tests/test_claude_code_litellm.sh
```

To include direct Bedrock alias calls in the LiteLLM smoke test:

```bash
RUN_BEDROCK_TESTS=1 ./tests/test_litellm_gateway.py
```

Claude Code note:

- LiteLLM's Anthropic-compatible `/v1/messages` route is validated by `test_claude_code_litellm.sh`.
- The installed Claude Code native binary in this environment did not honor `ANTHROPIC_BASE_URL`, `CLAUDE_CODE_API_BASE_URL`, or `BASE_API_URL`; it attempted to use Anthropic-hosted API directly and rejected `coding-default` as an invalid hosted model.
- The actual CLI probe is therefore opt-in:

```bash
RUN_CLAUDE_CLI_TEST=1 ./tests/test_claude_code_litellm.sh
```
