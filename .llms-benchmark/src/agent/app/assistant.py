"""The pydantic-ai agent: answers a catalog question using the MCP tools."""

from __future__ import annotations

import logging
import os

from opentelemetry import metrics, trace
from pydantic_ai import Agent, InstrumentationSettings
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from . import telemetry, throttle

LOG = logging.getLogger("llmbench.agent")

MODEL_NAME = os.environ.get("MODEL_NAME", "google/gemini-3.5-flash-lite")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
MCP_URL = os.environ.get("MCP_URL", "http://localhost:8081/mcp")
MODEL_ATTEMPTS = int(os.environ.get("MODEL_ATTEMPTS", "3"))

INSTRUCTIONS = """\
You are the store assistant of an outdoor and home-goods catalog.

Answer the customer's question using the catalog tools: search_products to
find products, get_product for one SKU, get_order to look an order up, and
place_order to buy. Quote SKUs and prices exactly as the tools return them,
in euros (the tools speak cents). Keep the answer under six sentences, and
say plainly when the catalog has no answer rather than inventing one.
"""

_agent: Agent | None = None


def _build_agent() -> Agent:
    provider = OpenAIProvider(
        base_url=OPENAI_BASE_URL,
        api_key=os.environ.get("OPENAI_API_KEY", ""),
    )
    model = OpenAIChatModel(MODEL_NAME, provider=provider)
    return Agent(
        model,
        instructions=INSTRUCTIONS,
        toolsets=[MCPToolset(MCP_URL)],
        name="llmbench-store-assistant",
    )


def instrument() -> None:
    """Turn on pydantic-ai's GenAI instrumentation.

    Called after the SDK is installed, so the settings capture the real
    providers rather than the no-op ones the API hands out at import time.
    """
    Agent.instrument_all(
        InstrumentationSettings(
            tracer_provider=trace.get_tracer_provider(),
            meter_provider=metrics.get_meter_provider(),
        )
    )


def get_agent() -> Agent:
    global _agent
    if _agent is None:
        _agent = _build_agent()
        LOG.info("agent built model=%s mcp=%s", MODEL_NAME, MCP_URL)
    return _agent


async def ask(question: str) -> dict:
    """Run one question through the agent and return its answer."""
    with telemetry.tracer().start_as_current_span("agent.ask") as span:
        span.set_attribute("question.length", len(question))

        throttle.wait_for_slot()

        last_error: Exception | None = None
        for attempt in range(1, MODEL_ATTEMPTS + 1):
            try:
                result = await get_agent().run(question)
            except Exception as error:  # noqa: BLE001 - a retry is cheaper than a 500
                last_error = error
                LOG.warning(
                    "model call failed attempt=%s/%s error=%s",
                    attempt,
                    MODEL_ATTEMPTS,
                    error,
                )
                continue

            usage = result.usage
            span.set_attribute("answer.length", len(str(result.output)))
            LOG.info(
                "answered question_len=%s answer_len=%s requests=%s tool_calls=%s",
                len(question),
                len(str(result.output)),
                usage.requests,
                usage.tool_calls,
            )
            return {
                "answer": result.output,
                "model": MODEL_NAME,
                "requests": usage.requests,
                "tool_calls": usage.tool_calls,
            }

        raise RuntimeError(
            f"model call failed after {MODEL_ATTEMPTS} attempts: {last_error}"
        )
