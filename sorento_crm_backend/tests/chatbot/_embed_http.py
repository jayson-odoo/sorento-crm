"""Shared test seam: route the one embeddings transport (httpx.Client.send, used by embedding_client.embed_texts)
to a fake `create(model=, input=)` shaped like the old OpenAI SDK stub, so a test keeps its call recording,
gating and sleeping. Vectors must be 1536 wide."""
from __future__ import annotations

import json

import httpx


def patch_openai_embeddings(monkeypatch, create) -> None:
    def send(self, request, **_kw):
        body = json.loads(request.content)
        result = create(model=body["model"], input=body["input"])
        data = [{"index": i, "embedding": list(item.embedding)} for i, item in enumerate(result.data)]
        return httpx.Response(200, json={"data": data}, request=request)

    monkeypatch.setattr(httpx.Client, "send", send)
