"""Live check for GEMINI-EXPLICIT-CACHE: does a model take an explicit cache with the parser's call shape?

Run by hand with a real key (costs well under one cent: a ~5k-token prompt, three short calls):

    GEMINI_API_KEY=... REDIS_URL=redis://localhost:6379/15 \
        venv/bin/python scripts/gemini_cache_live_check.py [model]

It sends three calls through `GeminiProvider.chat` with a JSON schema and a `prompt_cache_key`,
as the parser does, and prints what Google reported. Expected: call 1 creates the entry, calls
2 and 3 report `cached_tokens` near the prompt size. "create failed" in the log with
`cached_tokens 0` means the model refuses explicit caching, and calls fall back to uncached.
The entry is deleted at the end so it bills no storage.
"""
from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("JWT_SECRET", "live-check-only")
os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

from app.services import gemini_context_cache  # noqa: E402
from app.services.llm_provider import GeminiProvider  # noqa: E402

SCHEMA = {
    "type": "object",
    "properties": {"domain_hint": {"type": ["string", "null"]}, "quantity": {"type": ["integer", "null"]}},
    "required": ["domain_hint", "quantity"],
}


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    model = sys.argv[1] if len(sys.argv) > 1 else "gemini-3.5-flash-lite"
    rule = "R-{n} Read the user's message for the product they ask about and the quantity they want. "
    system = "".join(rule.format(n=n) for n in range(400)) + "\nCURRENT DATE: Tuesday, 28 October 2026"
    provider = GeminiProvider(os.environ["GEMINI_API_KEY"], default_model=model)
    for n, text in enumerate(["stock for SRT123?", "need 5 units of SRT123", "how about SRT999"], 1):
        result = provider.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": text}],
            json_schema=SCHEMA,
            max_tokens=200,
            timeout=20.0,
            prompt_cache_key="live_check:v1",
        )
        print(
            f"call {n}: prompt {result.prompt_tokens}, cached {result.cached_tokens}, "
            f"answer {result.content}"
        )
    key = gemini_context_cache.cache_key(
        provider.api_key, model, {"parts": [{"text": system}]}, None
    )
    name = gemini_context_cache.lookup(key)
    if name and name != gemini_context_cache.FAILED:
        provider._request("DELETE", name)
        gemini_context_cache.forget(key, name)
        print(f"deleted {name}")


if __name__ == "__main__":
    main()
