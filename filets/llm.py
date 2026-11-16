"""Thin Ollama client: structured JSON replies plus cost accounting."""

import hashlib
import json
import threading
import time
from dataclasses import dataclass

import httpx

OLLAMA_URL = "http://localhost:11434/api/chat"
EMBED_URL = "http://localhost:11434/api/embed"
EMBED_MODEL = "nomic-embed-text"
MAX_ATTEMPTS = 2
TEMPERATURE = 0.7
NUM_CTX = 4096
NUM_PREDICT = 200


class LLMFailure(Exception):
    """The model gave no usable reply after every attempt."""


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    failed_attempts: int = 0
    embed_calls: int = 0
    embed_tokens: int = 0
    embed_seconds: float = 0.0
    max_input_tokens: int = 0


def derive_seed(run_seed: int, season: int, fisher: int, call: int, attempt: int) -> int:
    """Seed of one attempt, set by its place in the run and not by what happened before it."""
    digest = hashlib.sha256(f"{run_seed}:{season}:{fisher}:{call}:{attempt}".encode()).digest()
    return int.from_bytes(digest[:4], "big") >> 1  # 31 bits


class LLMClient:
    def __init__(self, seed: int):
        self.seed = seed
        self.usage = Usage()
        self.lock = threading.Lock()
        self.http = httpx.Client(timeout=120)

    def ask(self, model: str, system: str, user: str, schema: dict, season: int, fisher: int, call: int) -> dict:
        """Ask once per attempt. A retry changes its own seed only, never those of later calls."""
        for attempt in range(MAX_ATTEMPTS):
            seed = derive_seed(self.seed, season, fisher, call, attempt)
            try:
                return self._attempt(model, system, user, schema, seed)
            except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError, ValueError):
                with self.lock:
                    self.usage.failed_attempts += 1
        raise LLMFailure(model)

    def embed(self, texts: list[str]) -> list[list[float]]:
        for _ in range(MAX_ATTEMPTS):
            started = time.perf_counter()
            try:
                response = self.http.post(EMBED_URL, json={"model": EMBED_MODEL, "input": texts})
                response.raise_for_status()
                body = response.json()
                vectors = body["embeddings"]
            except (httpx.HTTPError, json.JSONDecodeError, KeyError):
                with self.lock:
                    self.usage.failed_attempts += 1
                continue
            with self.lock:
                self.usage.embed_calls += 1
                self.usage.embed_tokens += body.get("prompt_eval_count", 0)
                self.usage.embed_seconds += time.perf_counter() - started
            return vectors
        raise LLMFailure(EMBED_MODEL)

    def _attempt(self, model: str, system: str, user: str, schema: dict, seed: int) -> dict:
        started = time.perf_counter()
        response = self.http.post(OLLAMA_URL, json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "format": schema,
            "stream": False,
            "options": {"temperature": TEMPERATURE, "seed": seed, "num_ctx": NUM_CTX, "num_predict": NUM_PREDICT},
        })
        response.raise_for_status()
        body = response.json()
        with self.lock:
            self.usage.calls += 1
            self.usage.input_tokens += body.get("prompt_eval_count", 0)
            self.usage.max_input_tokens = max(self.usage.max_input_tokens, body.get("prompt_eval_count", 0))
            self.usage.output_tokens += body.get("eval_count", 0)
            self.usage.seconds += time.perf_counter() - started

        data = json.loads(body["message"]["content"])
        for key in schema["required"]:
            if key not in data:
                raise KeyError(key)
        data["served_model"] = body.get("model")
        data["seed"] = seed
        return data
