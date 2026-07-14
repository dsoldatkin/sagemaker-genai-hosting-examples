# AgentCore Runtime deployment — Multi-Agent Financial Advisor
# Financial Analysis Agent uses Qwen 3.5 9B via SageMaker OpenAI-compatible API

import os

# Enable OpenTelemetry instrumentation for Strands Agents
os.environ.setdefault("AGENT_OBSERVABILITY_ENABLED", "true")

import yfinance as yf
import httpx
from openai import AsyncOpenAI
from typing import List

from strands import Agent, tool
from strands.models import BedrockModel
from strands.models.openai import OpenAIModel
from strands.agent.conversation_manager import SummarizingConversationManager
from sagemaker.core.token_generator import generate_token
from bedrock_agentcore import BedrockAgentCoreApp

from budget_agent import FinancialReport

# --- Configuration ---
from pathlib import Path
from dotenv import load_dotenv

# Load endpoint config from .env file (shared with deployment notebook)
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

SAGEMAKER_ENDPOINT_NAME = os.environ["SAGEMAKER_ENDPOINT_NAME"]
SAGEMAKER_REGION = os.environ["AWS_REGION"]


# --- SageMaker OpenAI-Compatible Client Setup ---
class SageMakerAuth(httpx.Auth):
    """Auto-refreshing auth that generates a fresh bearer token on each request."""
    def __init__(self, region: str):
        self.region = region

    def auth_flow(self, request):
        request.headers["Authorization"] = f"Bearer {generate_token(region=self.region)}"
        yield request


base_url = f"https://runtime.sagemaker.{SAGEMAKER_REGION}.amazonaws.com/endpoints/{SAGEMAKER_ENDPOINT_NAME}/openai/v1"
async_http_client = httpx.AsyncClient(auth=SageMakerAuth(region=SAGEMAKER_REGION))
strands_client = AsyncOpenAI(
    base_url=base_url,
    api_key="sagemaker",
    http_client=async_http_client,
)

qwen_model = OpenAIModel(
    client=strands_client,
    model_id="",
    params={
        "temperature": 0.7,
        "max_tokens": 4096,
        "stream_options": {"include_usage": True},
    },
)


# --- Financial Analysis Tools ---
@tool
def get_stock_analysis(symbol: str) -> str:
    """Get comprehensive analysis for a specific stock symbol."""
    try:
        stock = yf.Ticker(symbol)
        info = stock.info
        hist = stock.history(period="1y")
        if hist.empty:
            return f"No data available for {symbol}"
        current_price = hist["Close"].iloc[-1]
        year_high = hist["High"].max()
        year_low = hist["Low"].min()
        avg_volume = hist["Volume"].mean()
        price_change = ((current_price - hist["Close"].iloc[0]) / hist["Close"].iloc[0]) * 100
        return (
            f"Stock Analysis for {symbol.upper()}: "
            f"Price=${current_price:.2f}, 52W High=${year_high:.2f}, 52W Low=${year_low:.2f}, "
            f"YTD Change={price_change:.2f}%, Avg Volume={avg_volume:,.0f}, "
            f"Company={info.get('longName', 'N/A')}, Sector={info.get('sector', 'N/A')}"
        )
    except Exception as e:
        return f"Unable to retrieve data for {symbol}: {str(e)}"


@tool
def create_diversified_portfolio(risk_level: str, investment_amount: float) -> str:
    """Create a diversified portfolio based on risk level (conservative, moderate, aggressive) and investment amount."""
    portfolios = {
        "conservative": {"stocks": ["AAPL", "MSFT", "JNJ", "PG", "KO"], "weights": [0.25, 0.25, 0.20, 0.15, 0.15]},
        "moderate": {"stocks": ["AAPL", "GOOGL", "AMZN", "TSLA", "NVDA"], "weights": [0.30, 0.25, 0.20, 0.15, 0.10]},
        "aggressive": {"stocks": ["TSLA", "NVDA", "AMZN", "GOOGL", "META"], "weights": [0.30, 0.25, 0.20, 0.15, 0.10]},
    }
    if risk_level.lower() not in portfolios:
        return "Risk level must be: conservative, moderate, or aggressive"
    p = portfolios[risk_level.lower()]
    result = f"{risk_level.upper()} Portfolio (${investment_amount:,.0f}): "
    for stock, weight in zip(p["stocks"], p["weights"]):
        result += f"{stock}={weight*100:.0f}%(${investment_amount*weight:,.0f}) "
    return result


@tool
def compare_stock_performance(symbols: List[str], period: str = "1y") -> str:
    """Compare performance of multiple stocks over a specified period."""
    if len(symbols) > 5:
        return "Please limit comparison to 5 stocks maximum"
    try:
        results = []
        for symbol in symbols:
            hist = yf.Ticker(symbol).history(period=period)
            if not hist.empty:
                perf = ((hist["Close"].iloc[-1] - hist["Close"].iloc[0]) / hist["Close"].iloc[0]) * 100
                results.append(f"{symbol}: {perf:+.2f}%")
        return f"Performance Comparison ({period}): " + ", ".join(results)
    except Exception as e:
        return f"Error comparing stocks: {str(e)}"


# --- Financial Analysis Agent Prompt ---
FINANCIAL_ANALYSIS_PROMPT = """You are a specialized financial analysis agent focused on investment research and portfolio recommendations.
Research and analyze stock data, create diversified portfolios, and provide data-driven recommendations.
Always include disclaimers about market risks."""


# --- Agent Tools for Orchestrator ---
@tool
def budget_agent_tool(query: str) -> FinancialReport:
    """Generate structured financial reports with budget analysis and recommendations."""
    try:
        # Import tools from budget_agent module and create a fresh instance
        from budget_agent import (
            calculate_budget_breakdown, analyze_spending_pattern, calculator,
            BUDGET_AGENT_PROMPT,
        )
        fresh_budget_agent = Agent(
            model=BedrockModel(
                model_id="global.anthropic.claude-sonnet-4-6-20250514-v1:0",
                region_name=SAGEMAKER_REGION,
                temperature=0.0,
            ),
            system_prompt=BUDGET_AGENT_PROMPT,
            tools=[calculate_budget_breakdown, analyze_spending_pattern, calculator],
            callback_handler=None,
        )
        return fresh_budget_agent(query, output_model=FinancialReport)
    except Exception as e:
        return FinancialReport(
            monthly_income=0.0, budget_categories=[],
            recommendations=[f"Error: {str(e)}"], financial_health_score=1,
        )


@tool
def financial_analysis_agent_tool(query: str) -> str:
    """Handle investment analysis queries including stock research, portfolio creation, and performance comparisons."""
    from opentelemetry import trace

    tracer = trace.get_tracer("financial_analysis_agent")

    try:
        # Create a fresh agent instance per invocation to avoid
        # "Agent is already processing a request" concurrent invocation error
        fa_agent = Agent(
            model=OpenAIModel(
                client=strands_client,
                model_id="",
                params={
                    "temperature": 0.7,
                    "max_tokens": 4096,
                    "stream_options": {"include_usage": True},
                },
            ),
            system_prompt=FINANCIAL_ANALYSIS_PROMPT,
            tools=[get_stock_analysis, create_diversified_portfolio, compare_stock_performance],
            callback_handler=None,
        )

        with tracer.start_as_current_span("gen_ai.chat", attributes={
            "gen_ai.system": "openai",
            "gen_ai.request.model": f"qwen3.5-9b ({SAGEMAKER_ENDPOINT_NAME})",
            "gen_ai.operation.name": "chat",
        }) as span:
            result = fa_agent(query)
            # Extract token usage from accumulated_usage in agent metrics
            usage = result.metrics.accumulated_usage
            input_tokens = usage.get('inputTokens', 0)
            output_tokens = usage.get('outputTokens', 0)
            total_tokens = usage.get('totalTokens', 0)

            span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
            span.set_attribute("gen_ai.usage.total_tokens", total_tokens)

            response = str(result)

        return f"[Routed to: Qwen 3.5 9B on SageMaker endpoint '{SAGEMAKER_ENDPOINT_NAME}' via OpenAI-compatible API]\n\n{response}"
    except Exception as e:
        return f"Financial analysis error: {str(e)}"


# --- Orchestrator Agent (Claude Haiku 4.5 via Bedrock) ---
ORCHESTRATOR_PROMPT = """You are a financial advisor orchestrator coordinating specialized agents.
Use budget_agent_tool for budgets, spending, savings. Use financial_analysis_agent_tool for stocks, portfolios, investments.
You can use both together. Synthesize coherent answers with actionable next steps."""

orchestrator_model = BedrockModel(
    model_id="global.anthropic.claude-haiku-4-5-20251001-v1:0",
    region_name=SAGEMAKER_REGION,
    temperature=0.0,
)


# --- AgentCore Runtime Entrypoint ---
app = BedrockAgentCoreApp()


@app.entrypoint
async def invoke(payload):
    """AgentCore Runtime invocation handler with streaming."""
    # Create a fresh orchestrator per request to avoid concurrent invocation errors
    orchestrator = Agent(
        model=orchestrator_model,
        system_prompt=ORCHESTRATOR_PROMPT,
        tools=[budget_agent_tool, financial_analysis_agent_tool],
        conversation_manager=SummarizingConversationManager(
            summary_ratio=0.3, preserve_recent_messages=5,
        ),
    )
    user_message = payload["prompt"]
    async for event in orchestrator.stream_async(user_message):
        if "data" in event:
            yield event["data"]


if __name__ == "__main__":
    app.run()

