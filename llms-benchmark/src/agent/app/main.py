"""llmbench-agent - the HTTP front of the llms-benchmark demo agent."""

from __future__ import annotations

import logging
import os

import uvicorn
from fastapi import FastAPI, HTTPException
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPX2ClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from pydantic import BaseModel

from . import assistant, telemetry

LOG = logging.getLogger("llmbench.agent")

app = FastAPI(title="llmbench-agent", version="0.1.0")

_questions = None


class Question(BaseModel):
    question: str


@app.on_event("startup")
def _startup() -> None:
    global _questions
    _questions = telemetry.meter().create_counter(
        "agent.questions",
        unit="{question}",
        description="Questions the agent was asked",
    )


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": telemetry.SERVICE_NAME,
        "model": assistant.MODEL_NAME,
    }


@app.post("/ask")
async def ask(payload: Question) -> dict:
    if _questions is not None:
        _questions.add(1, {"gen_ai.request.model": assistant.MODEL_NAME})
    try:
        return await assistant.ask(payload.question)
    except Exception as error:
        LOG.error("ask failed error=%s", error)
        raise HTTPException(status_code=500, detail=str(error)) from error


def main() -> None:
    for noisy in ("httpx", "httpx2", "httpcore", "httpcore2"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    telemetry.setup_telemetry()
    LoggingInstrumentor().instrument(set_logging_format=False, log_code_attributes=True)
    # httpx2, not httpx: the model SDK, pydantic-ai and the MCP client all
    # speak httpx2, and the v1 instrumentor would patch a library nothing
    # on this path calls - leaving the model call with no client span and
    # no client duration metric.
    HTTPX2ClientInstrumentor().instrument()
    FastAPIInstrumentor.instrument_app(app)
    assistant.instrument()
    try:
        uvicorn.run(
            app,
            host="0.0.0.0",  # a container port, published deliberately
            port=int(os.environ.get("PORT", "8080")),
            log_config=None,
        )
    finally:
        telemetry.shutdown_telemetry()


if __name__ == "__main__":
    main()
