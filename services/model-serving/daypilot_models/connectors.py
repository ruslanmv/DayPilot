from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

import httpx


class ModelBackend(Protocol):
    name: str

    def generate(self, prompt: str, task: str = "general") -> dict: ...


@dataclass
class MockBackend:
    name: str = "mock"

    def generate(self, prompt: str, task: str = "general") -> dict:
        return {
            "backend": self.name,
            "task": task,
            "text": f"[mock response] task={task}; prompt={prompt[:120]}",
            "tokens": {"input_estimate": len(prompt.split()), "output_estimate": 8},
        }


@dataclass
class OllamaBackend:
    base_url: str
    model: str
    name: str = "ollama"

    def generate(self, prompt: str, task: str = "general") -> dict:
        with httpx.Client(timeout=60) as client:
            response = client.post(
                f"{self.base_url.rstrip('/')}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
            )
            response.raise_for_status()
            data = response.json()
        return {"backend": self.name, "task": task, "model": self.model, "text": data.get("response", ""), "raw": data}


@dataclass
class OpenAICompatibleBackend:
    base_url: str
    model: str
    api_key: str | None = None
    name: str = "openai-compatible"

    def generate(self, prompt: str, task: str = "general") -> dict:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        with httpx.Client(timeout=60) as client:
            response = client.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                },
            )
            response.raise_for_status()
            data = response.json()
        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {"backend": self.name, "task": task, "model": self.model, "text": text, "raw": data}


def load_backend() -> ModelBackend:
    backend = os.getenv("DAYPILOT_MODEL_BACKEND", "mock").lower()
    if backend == "ollama":
        return OllamaBackend(
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            model=os.getenv("OLLAMA_MODEL", "llama3.1"),
        )
    if backend in {"vllm", "openai-compatible", "openai_compatible"}:
        return OpenAICompatibleBackend(
            base_url=os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1"),
            model=os.getenv("VLLM_MODEL", "local-model"),
            api_key=os.getenv("VLLM_API_KEY"),
            name="vllm",
        )
    return MockBackend()
