"""Budget Agent — powered by Claude Sonnet 4.6 via Amazon Bedrock Global CRIS.

Specializes in personal budgeting, spending analysis, and financial discipline.
"""

from strands import Agent, tool
from strands.models import BedrockModel
from pydantic import BaseModel, Field
from typing import List


# --- Pydantic models for structured output ---

class BudgetCategory(BaseModel):
    category: str = Field(description="Budget category name")
    amount: float = Field(description="Allocated amount")
    percentage: float = Field(description="Percentage of total income")


class FinancialReport(BaseModel):
    monthly_income: float = Field(description="Monthly income")
    budget_categories: List[BudgetCategory] = Field(description="Budget breakdown")
    recommendations: List[str] = Field(description="Financial recommendations")
    financial_health_score: int = Field(description="Score from 1-10", ge=1, le=10)


# --- Budget Tools ---

@tool
def calculate_budget_breakdown(monthly_income: float) -> str:
    """Calculate a 50/30/20 budget breakdown for any income level.

    The 50/30/20 rule allocates:
    - 50% to Needs (housing, groceries, utilities, insurance)
    - 30% to Wants (dining, entertainment, subscriptions)
    - 20% to Savings & Debt (emergency fund, investments, debt payoff)
    """
    needs = monthly_income * 0.50
    wants = monthly_income * 0.30
    savings = monthly_income * 0.20

    return f"""
💰 50/30/20 Budget Breakdown for ${monthly_income:,.0f}/month:

📋 NEEDS (50%): ${needs:,.0f}
  • Housing: ${monthly_income * 0.28:,.0f} (28%)
  • Groceries: ${monthly_income * 0.10:,.0f} (10%)
  • Utilities: ${monthly_income * 0.05:,.0f} (5%)
  • Transportation: ${monthly_income * 0.04:,.0f} (4%)
  • Insurance: ${monthly_income * 0.03:,.0f} (3%)

🎯 WANTS (30%): ${wants:,.0f}
  • Dining Out: ${monthly_income * 0.10:,.0f} (10%)
  • Entertainment: ${monthly_income * 0.08:,.0f} (8%)
  • Shopping: ${monthly_income * 0.07:,.0f} (7%)
  • Subscriptions: ${monthly_income * 0.05:,.0f} (5%)

🏦 SAVINGS & DEBT (20%): ${savings:,.0f}
  • Emergency Fund: ${monthly_income * 0.10:,.0f} (10%)
  • Investments: ${monthly_income * 0.05:,.0f} (5%)
  • Debt Payoff: ${monthly_income * 0.05:,.0f} (5%)
"""


@tool
def analyze_spending_pattern(category: str, amount: float, monthly_income: float) -> str:
    """Analyze a spending pattern and provide recommendations.

    Compares actual spending in a category against recommended guidelines.
    """
    percentage = (amount / monthly_income) * 100

    # Recommended maximums by category
    recommended = {
        "housing": 28, "rent": 28, "mortgage": 28,
        "groceries": 12, "food": 12,
        "dining": 10, "restaurants": 10, "eating out": 10,
        "transportation": 15, "car": 15,
        "entertainment": 8,
        "shopping": 7,
        "utilities": 5,
        "subscriptions": 5,
    }

    category_lower = category.lower()
    max_recommended = recommended.get(category_lower, 10)
    status = "✅ Within budget" if percentage <= max_recommended else "⚠️ Over budget"
    overspend = max(0, amount - (monthly_income * max_recommended / 100))

    return f"""
📊 Spending Analysis: {category.title()}

• Amount: ${amount:,.0f}/month
• Percentage of Income: {percentage:.1f}%
• Recommended Maximum: {max_recommended}%
• Status: {status}
{"• Overspend: $" + f"{overspend:,.0f}/month" if overspend > 0 else ""}

💡 Recommendations:
{"- Consider reducing " + category + " spending by $" + f"{overspend:,.0f}" if overspend > 0 else "- Great job staying within budget!"}
- Track daily expenses in this category for a week
- Look for alternatives or discounts
"""


@tool
def calculator(expression: str) -> str:
    """Perform financial calculations. Supports basic math operations."""
    try:
        # Safe evaluation of mathematical expressions
        allowed_chars = set("0123456789+-*/.() ")
        if not all(c in allowed_chars for c in expression):
            return "❌ Invalid expression. Use numbers and +, -, *, / operators only."
        result = eval(expression)
        return f"🧮 {expression} = {result:,.2f}"
    except Exception as e:
        return f"❌ Calculation error: {str(e)}"


# --- Agent Configuration ---

BUDGET_AGENT_PROMPT = """You are a specialized personal finance and budgeting agent. Your role is to:

1. Create detailed budget breakdowns using the 50/30/20 rule
2. Analyze spending patterns and identify areas for improvement
3. Provide actionable savings recommendations
4. Help users understand their financial health

Always be encouraging but honest. Use data from your tools to support recommendations.
When users share their income, immediately create a budget breakdown.
When they share spending details, analyze the pattern against their income."""

# Claude Sonnet 4.6 via Bedrock Global CRIS
bedrock_model = BedrockModel(
    model_id="global.anthropic.claude-sonnet-4-6-20250514-v1:0",
    region_name="us-west-2",
    temperature=0.0,
)

budget_agent = Agent(
    model=bedrock_model,
    system_prompt=BUDGET_AGENT_PROMPT,
    tools=[calculate_budget_breakdown, analyze_spending_pattern, calculator],
    callback_handler=None,
)

if __name__ == "__main__":
    response = budget_agent("Create a budget for my $6000 monthly income")
    print(response)
