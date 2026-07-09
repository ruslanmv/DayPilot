from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.responses import Response

from daypilot_models.connectors import load_backend

GENERATIONS = Counter("daypilot_model_generations_total", "Model generation calls", ["backend"])
GENERATION_LATENCY = Histogram("daypilot_model_generation_seconds", "Model generation latency", ["backend"])


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    task: str = "general"


def route_model(task: str) -> dict:
    backend = load_backend()
    return {
        "task": task,
        "backend": backend.name,
        "candidates": ["mock", "ollama", "vllm", "openai-compatible"],
        "policy": "local-first unless explicitly configured otherwise",
    }


def generate(prompt: str, task: str = "general") -> dict:
    backend = load_backend()
    with GENERATION_LATENCY.labels(backend=backend.name).time():
        result = backend.generate(prompt=prompt, task=task)
    GENERATIONS.labels(backend=backend.name).inc()
    return result


app = FastAPI(title="DayPilot Model Serving", version="0.2.0")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "daypilot-model-serving", "router": route_model("health")}


@app.get("/v1/models/route/{task}")
def route(task: str) -> dict:
    return route_model(task)


@app.post("/v1/generate")
def create_generation(request: GenerateRequest) -> dict:
    return generate(request.prompt, request.task)


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
