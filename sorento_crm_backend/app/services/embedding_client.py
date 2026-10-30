"""The one place that posts to an embeddings endpoint (LOOKUP-EMBED-CENTRAL, AC-LEC-4).

`embed_texts` returns unit-length vectors, always `EMBEDDING_DIMENSIONS` wide, whichever provider
answers; a vector of any other width raises `EmbeddingDimensionError` instead of reaching a
pgvector column. Callers keep their own caching, chunking policy, retry waits and key lookup.
"""
from __future__ import annotations

import math
from typing import Any, Optional

import httpx

from app.config import settings

EMBEDDING_DIMENSIONS = 1536
#: Gemini's batchEmbedContents takes at most 100 texts per request.
GEMINI_BATCH = 100
#: The OpenAI embeddings endpoint takes at most 2048 inputs per request.
OPENAI_BATCH = 2048
DEFAULT_TIMEOUT = 30.0


class EmbeddingDimensionError(ValueError):
    """A provider returned a vector that is not `EMBEDDING_DIMENSIONS` long."""


class EmbeddingHTTPError(RuntimeError):
    """A refused embeddings call, with its HTTP status as `status_code` (the chatbot's retry seam reads it)."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


def _post(client: httpx.Client, url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
    try:
        response = client.post(url, headers=headers, json=body)
    except httpx.HTTPError as exc:  # network-level failure
        raise RuntimeError(f"Embedding request failed: {exc}") from exc
    if response.status_code >= 400:
        raise EmbeddingHTTPError(
            f"Embedding call failed ({response.status_code}): {(response.text or '')[:300]}",
            response.status_code,
        )
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError("Embedding provider returned a non-JSON response.") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Embedding provider returned an unexpected response shape.")
    return data


def _unit(vector: list[float]) -> list[float]:
    if len(vector) != EMBEDDING_DIMENSIONS:
        raise EmbeddingDimensionError(
            f"Embedding has {len(vector)} dimensions, expected {EMBEDDING_DIMENSIONS}."
        )
    magnitude = math.sqrt(sum(v * v for v in vector))
    if not magnitude:
        return vector
    return [v / magnitude for v in vector]


def _gemini(texts: list[str], model: str, api_key: str, timeout: float) -> list[list[float]]:
    from app.services.llm_provider import GEMINI_API_BASE

    out: list[list[float]] = []
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    with httpx.Client(timeout=timeout) as client:
        for i in range(0, len(texts), GEMINI_BATCH):
            batch = texts[i : i + GEMINI_BATCH]
            body = _post(
                client,
                f"{GEMINI_API_BASE}/models/{model}:batchEmbedContents",
                headers,
                {
                    "requests": [
                        {
                            "model": f"models/{model}",
                            "content": {"parts": [{"text": t}]},
                            "outputDimensionality": EMBEDDING_DIMENSIONS,
                        }
                        for t in batch
                    ]
                },
            )
            vectors = [e.get("values") or [] for e in body.get("embeddings") or []]
            if len(vectors) != len(batch) or not all(vectors):
                raise RuntimeError("Gemini returned the wrong number of vectors.")
            out.extend(_unit([float(v) for v in vec]) for vec in vectors)
    return out


def _openai(texts: list[str], model: str, api_key: str, timeout: float) -> list[list[float]]:
    out: list[list[float]] = []
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=timeout) as client:
        for i in range(0, len(texts), OPENAI_BATCH):
            batch = texts[i : i + OPENAI_BATCH]
            payload: dict[str, Any] = {"model": model, "input": batch}
            if model.startswith("text-embedding-3") and model != "text-embedding-3-small":
                payload["dimensions"] = EMBEDDING_DIMENSIONS  # native size is larger
            data = _post(client, settings.openai_embeddings_url, headers, payload)
            items = sorted(data.get("data") or [], key=lambda item: item.get("index", 0))
            if len(items) != len(batch):
                raise ValueError("Embedding provider returned mismatched vector count")
            out.extend(_unit([float(v) for v in item["embedding"]]) for item in items)
    return out


def embed_texts(
    texts: list[str],
    provider: str,
    model: str,
    *,
    api_key: Optional[str] = None,
    timeout: Optional[float] = None,
) -> list[list[float]]:
    """Unit-length 1536-wide vectors for `texts`, in order. `api_key` None means the OpenAI key from settings."""
    if not texts:
        return []
    wait = timeout or DEFAULT_TIMEOUT
    if provider == "gemini":
        if not api_key:
            raise RuntimeError("No Gemini API key is configured.")
        return _gemini(list(texts), model, api_key, wait)
    if provider == "openai":
        key = api_key or settings.openai_api_key
        if not key:
            raise RuntimeError("No OpenAI API key is configured.")
        return _openai(list(texts), model, key, wait)
    raise ValueError(f"Unsupported embedding provider: {provider}")
