# SageMaker OpenAI-Compatible Endpoint with Strands Agents

Deploy open-source LLMs on Amazon SageMaker using the **OpenAI-compatible API** and build multi-agent systems with [Strands Agents](https://strandsagents.com/) — ultimately deploying to **Amazon Bedrock AgentCore Runtime**.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                  Amazon Bedrock AgentCore Runtime                │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              Orchestrator Agent (Claude Haiku 4.5)         │  │
│  │                    Bedrock (us-west-2)                     │  │
│  └────────────┬──────────────────────────┬───────────────────┘  │
│               │                          │                      │
│  ┌────────────▼────────────┐  ┌──────────▼───────────────────┐  │
│  │    Budget Agent         │  │  Financial Analysis Agent     │  │
│  │  (Claude Sonnet 4.6)   │  │  (Qwen 3.5 9B on SageMaker)  │  │
│  │    Bedrock              │  │  OpenAI-compatible API        │  │
│  └─────────────────────────┘  └──────────────────┬───────────┘  │
│                                              │                  │
└──────────────────────────────────────────────┼──────────────────┘
                                               │
                              ┌─────────────────▼─────────────────┐
                              │   SageMaker Endpoint (vLLM DLC)   │
                              │   Qwen 3.5 9B — ml.g6e.2xlarge    │
                              │   OpenAI-compatible: /openai/v1   │
                              └───────────────────────────────────┘
```

## Project Structure

```
sagemaker-open-ai-compatible-endpoints-agentcore-runtime/
├── README.md
├── Lab1-sagemaker-endpoint-qwen3.5-9B.ipynb   # Lab 1: Deploy & test SageMaker endpoint
├── Lab2/
│   ├── finance_multi_agent.ipynb              # Lab 2: Multi-agent orchestration
│   └── strands_agents/
│       └── budget_agent.py                    # Budget Agent module
└── Lab3/
    ├── deploy_agentcore.ipynb                 # Lab 3: Deploy to AgentCore Runtime
    ├── main.py                                # AgentCore entrypoint
    └── OBSERVABILITY.md                       # Observability guide
```

## How to Run

### Prerequisites

- AWS account with SageMaker, Bedrock, and AgentCore access
- SageMaker Studio environment (Python 3.12+)
- Bedrock model access for Claude Haiku 4.5 and Claude Sonnet 4.6
- Service quota for `ml.g6e.2xlarge` endpoint instances

### Lab 1: Deploy Qwen 3.5 9B on SageMaker

**Notebook**: `Lab1-sagemaker-endpoint-qwen3.5-9B.ipynb`

1. Run the notebook cells in order to:
   - Create an IAM role for the SageMaker endpoint
   - Deploy Qwen 3.5 9B using the vLLM DLC container (`vllm:0.22.1-gpu-py312-cu130`) on `ml.g6e.2xlarge`
   - Test non-streaming and streaming inference
   - Test the OpenAI-compatible API (`/openai/v1`) with auto-refreshing bearer tokens
   - Create a Strands Agent using `OpenAIModel` + `AsyncOpenAI` pointing to the endpoint

2. The notebook creates a `.env` file with `AWS_REGION` and `SAGEMAKER_ENDPOINT_NAME` — used by Lab 2 and Lab 3.

### Lab 2: Multi-Agent Financial Advisor

**Notebook**: `Lab2/finance_multi_agent.ipynb`

1. Loads endpoint config from `../.env` (created by Lab 1)
2. Creates specialized agents:
   - **Budget Agent** — Claude Sonnet 4.6 via Bedrock with budget/spending analysis tools
   - **Financial Analysis Agent** — Qwen 3.5 9B via SageMaker with stock analysis tools (yfinance)
3. Creates an **Orchestrator Agent** (Claude Haiku 4.5, us-west-2) that routes queries to the appropriate specialist using the "Agents as Tools" pattern
4. Tests the full multi-agent workflow

### Lab 3: Deploy to AgentCore Runtime

**Notebook**: `Lab3/deploy_agentcore.ipynb`

1. Copies `budget_agent.py` from Lab2 into the Lab3 folder (needed for container packaging)
2. Writes `main.py` — the AgentCore entrypoint with `BedrockAgentCoreApp`
3. Configures AgentCore Runtime (auto-creates execution role, ECR repo, Dockerfile)
4. Attaches SageMaker permissions to the execution role (`InvokeEndpoint`, `CallWithBearerToken`)
5. Launches the containerized agent to AgentCore
6. Invokes the agent via `boto3` with IAM SigV4 authentication

## Key Technical Patterns

| Pattern | Details |
|---------|---------|
| **OpenAI-compatible API** | `https://runtime.sagemaker.<REGION>.amazonaws.com/endpoints/<NAME>/openai/v1` |
| **Auto-refreshing tokens** | `httpx.Auth` subclass calls `generate_token()` on every request |
| **Strands + SageMaker** | `OpenAIModel` with `AsyncOpenAI` client — no custom provider needed |
| **Environment config** | `.env` file shared across labs with `python-dotenv` (`override=True`) |
| **AgentCore auth** | IAM SigV4 — invoke via `boto3` client directly |
| **Observability** | Custom `gen_ai.chat` OTel spans for SageMaker token usage metrics |

## Observability

See [`Lab3/OBSERVABILITY.md`](Lab3/OBSERVABILITY.md) for the full guide on configuring AgentCore observability with custom OpenTelemetry spans for SageMaker endpoint token usage.

## References

- [SageMaker OpenAI-compatible API](https://aws.amazon.com/blogs/machine-learning/announcing-openai-compatible-api-support-for-amazon-sagemaker-ai-endpoints/)
- [Strands Agents — Agents as Tools](https://strandsagents.com/latest/documentation/docs/user-guide/concepts/multi-agent/agents-as-tools/)
- [AgentCore Runtime Docs](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agents-tools-runtime.html)
- [AgentCore Observability](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-get-started.html)
