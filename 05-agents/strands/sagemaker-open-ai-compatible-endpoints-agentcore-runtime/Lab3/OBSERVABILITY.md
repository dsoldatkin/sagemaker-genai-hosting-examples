# AgentCore Observability for SageMaker OpenAI-Compatible Endpoints

This document explains how we configured Amazon Bedrock AgentCore Observability to capture full traces — including **input/output token metrics** — from a Qwen 3.5 9B model running on a SageMaker endpoint via the OpenAI-compatible API.

## The Challenge

AgentCore Runtime automatically instruments agents deployed on it using OpenTelemetry. However:

1. **Bedrock model calls** get full GenAI spans with token counts automatically
2. **SageMaker OpenAI-compatible endpoints** (via Strands `OpenAIModel`) do NOT get automatic token telemetry — the built-in instrumentation doesn't recognize them as GenAI model calls

This means that when the Financial Analysis Agent calls Qwen 3.5 9B on SageMaker, the tokens consumed are invisible in traces unless we manually emit them.

## Solution: Manual OpenTelemetry Spans

We create a custom `gen_ai.chat` span inside the `financial_analysis_agent_tool` that:
- Wraps the agent invocation
- Extracts token usage from Strands' `AgentResult.metrics.accumulated_usage`
- Sets GenAI semantic convention attributes on the span

```python
from opentelemetry import trace

tracer = trace.get_tracer("financial_analysis_agent")

with tracer.start_as_current_span("gen_ai.chat", attributes={
    "gen_ai.system": "openai",
    "gen_ai.request.model": f"qwen3.5-9b ({SAGEMAKER_ENDPOINT_NAME})",
    "gen_ai.operation.name": "chat",
}) as span:
    result = fa_agent(query)
    
    # Extract token usage from Strands agent metrics
    usage = result.metrics.accumulated_usage
    span.set_attribute("gen_ai.usage.input_tokens", usage.get('inputTokens', 0))
    span.set_attribute("gen_ai.usage.output_tokens", usage.get('outputTokens', 0))
    span.set_attribute("gen_ai.usage.total_tokens", usage.get('totalTokens', 0))
```

## Configuration Steps

### 1. Enable CloudWatch Transaction Search (one-time per account/region)

```bash
# Create resource policy for X-Ray to write spans
aws logs put-resource-policy \
  --region ap-south-1 \
  --policy-name TransactionSearchXRayAccess \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Sid": "TransactionSearchXRayAccess",
      "Effect": "Allow",
      "Principal": {"Service": "xray.amazonaws.com"},
      "Action": "logs:PutLogEvents",
      "Resource": [
        "arn:aws:logs:ap-south-1:ACCOUNT_ID:log-group:aws/spans:*",
        "arn:aws:logs:ap-south-1:ACCOUNT_ID:log-group:/aws/application-signals/data:*"
      ],
      "Condition": {
        "ArnLike": {"aws:SourceArn": "arn:aws:xray:ap-south-1:ACCOUNT_ID:*"},
        "StringEquals": {"aws:SourceAccount": "ACCOUNT_ID"}
      }
    }]
  }'

# Set trace destination to CloudWatch Logs
aws xray update-trace-segment-destination --region ap-south-1 --destination CloudWatchLogs

# Set sampling to 100% (optional, 1% is free tier)
aws xray update-indexing-rule --region ap-south-1 --name "Default" \
  --rule '{"Probabilistic": {"DesiredSamplingPercentage": 100}}'
```

### 2. Enable Observability in Agent Code (`main.py`)

```python
import os
os.environ.setdefault("AGENT_OBSERVABILITY_ENABLED", "true")
```

This activates the Strands OTEL pipeline inside the AgentCore container.

### 3. Install Strands with OTEL extras (`requirements.txt`)

```
strands-agents[otel]>=1.0.0
```

The `[otel]` extra installs OpenTelemetry dependencies that Strands uses to emit tool call events and agent lifecycle spans.

### 4. Enable Token Usage in Streaming Responses

```python
qwen_model = OpenAIModel(
    client=strands_client,
    model_id="",
    params={
        "temperature": 0.7,
        "max_tokens": 4096,
        "stream_options": {"include_usage": True},  # <-- vLLM sends token counts
    },
)
```

Without `stream_options: {"include_usage": True}`, vLLM does not include a `usage` chunk in streaming responses, and Strands cannot track token counts.

### 5. Deploy with `AGENT_OBSERVABILITY_ENABLED` Environment Variable

```python
launch_result = agentcore_runtime.launch(
    env_vars={
        "SAGEMAKER_ENDPOINT_NAME": "qwen35-9b-260612-082732",
        "SAGEMAKER_REGION": "ap-south-1",
        "AGENT_OBSERVABILITY_ENABLED": "true",
    }
)
```

## What Gets Traced

After all configuration, the following appears in AgentCore Observability:

| Span/Event | Source | Contains |
|------------|--------|----------|
| `AgentCore.Runtime.Invoke` | AgentCore platform | Request metadata, session ID, latency |
| `strands.telemetry.tracer` (tool events) | Strands OTEL | Tool input/output messages |
| `botocore.credentials` (log) | ADOT auto-instrumentation | IAM role credential resolution |
| `gen_ai.chat` | **Custom span (our code)** | `input_tokens`, `output_tokens`, `total_tokens`, model name |

### Example Trace Output

```json
{
  "name": "gen_ai.chat",
  "attributes": {
    "gen_ai.system": "openai",
    "gen_ai.request.model": "qwen3.5-9b (qwen35-9b-260612-082732)",
    "gen_ai.operation.name": "chat",
    "gen_ai.usage.input_tokens": 1391,
    "gen_ai.usage.output_tokens": 1432,
    "gen_ai.usage.total_tokens": 2823
  },
  "durationNano": 37237386894
}
```

## Key Learnings

1. **AgentCore auto-instruments Bedrock calls** — no extra work needed for Claude/Nova models
2. **SageMaker OpenAI endpoints need manual spans** — the platform doesn't recognize them as GenAI calls
3. **Token usage requires `stream_options`** — vLLM doesn't send usage in streaming mode by default
4. **Use `result.metrics.accumulated_usage`** — Strands tracks tokens internally in this dict with keys `inputTokens`, `outputTokens`, `totalTokens`
5. **Sampling rate matters** — at 1% default, most traces are dropped; set to 100% during development
6. **Fresh agent instances per request** — module-level Agent singletons cause "concurrent invocation" errors when called as tools inside another agent's event loop
