"""CHAT-LATENCY-SCOUT (documentation/plans/chatbot/CARD-chat-latency-scout-20oct.md).

B: the spec reading (`product_spec_understanding.understand_phrase`) sits on the chatbot
reply path, after the resolver code reader, and asked the provider with NO timeout - the SDK
default of 600 s with two silent retries. It now gets the code reader's own 3 s budget, which
also turns the SDK retries off (`llm_provider.chat`: a caller timeout means max_retries=0). A
timeout ends in the deterministic reading, the same arm any provider failure already takes,
so the turn answers from the literal words instead of waiting.

C: `OpenAIProvider._client` built a new `OpenAI` (and so a new TCP + TLS connection) on every
call. One client is now kept per (key, timeout, retries, base_url), shared across threads.
"""
from __future__ import annotations

import json
import threading
import uuid
from types import SimpleNamespace

import pytest

from app.models.product import ProductCategory, UnitOfMeasure
from app.services import llm_provider
from app.services import product_spec_understanding as understanding
from app.services.product_class_signal import backfill_category_signals
from app.services.product_spec_registry import seed_spec_registry
from tests._pg_fixture import blank_session


@pytest.fixture
def db():
    with blank_session() as s:
        s.add_all(
            [
                ProductCategory(id=str(uuid.uuid4()), category_code="SRT-KS", category_name="SRT-KS"),
                UnitOfMeasure(id=str(uuid.uuid4()), uom_code="ZZT-PCS", uom_name="Piece"),
            ]
        )
        s.flush()
        backfill_category_signals(s)
        seed_spec_registry(s)
        yield s


# --------------------------------------------------------------------------- #
# B: the spec reading's budget
# --------------------------------------------------------------------------- #
def test_the_spec_reading_asks_the_provider_with_the_code_readers_budget(db, monkeypatch):
    seen: list[dict] = []
    result = SimpleNamespace(content=json.dumps({"specs": []}), prompt_tokens=1, completion_tokens=1, total_tokens=2)

    def chat(*_a, **kwargs):
        seen.append(kwargs)
        return result

    monkeypatch.setattr(
        understanding, "_resolve_provider", lambda db: (SimpleNamespace(chat=chat), "openai", "gpt-test")
    )

    # CHAT-RELEASE-1021 (crew review fix 2 of #1809): the budget is the chatbot turn's, passed by
    # the resolve endpoint only (`tests/test_chat_latency_scope.py`); the CRM preview keeps none.
    understanding.understand_phrase(
        db, "a stainless steel kitchen sink", model_timeout=understanding.CHAT_TURN_MODEL_TIMEOUT_SECONDS
    )

    assert len(seen) == 1
    assert seen[0].get("timeout") == pytest.approx(3.0), "no timeout means the SDK's 600 s and 2 retries"


def test_a_spec_reading_timeout_ends_in_the_deterministic_reading(db, monkeypatch):
    """Never stuck: the turn gets the literal reading and goes on to the ranker."""
    from openai import APITimeoutError

    def chat(*_a, **_k):
        raise APITimeoutError("Request timed out.")

    monkeypatch.setattr(
        understanding, "_resolve_provider", lambda db: (SimpleNamespace(chat=chat), "openai", "gpt-test")
    )

    reading = understanding.understand_phrase(db, "a stainless steel kitchen sink")

    assert reading.source == "deterministic"
    assert reading.free_terms[0] == "a stainless steel kitchen sink"


# --------------------------------------------------------------------------- #
# C: one OpenAI client per (key, timeout, retries, base_url)
# --------------------------------------------------------------------------- #
class _Completions:
    def create(self, **_kwargs):
        message = SimpleNamespace(content="ok", tool_calls=None)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2, prompt_tokens_details=None),
            model="gpt-test",
        )


def _counting_openai(monkeypatch) -> list[dict]:
    built: list[dict] = []

    def factory(**kwargs):
        built.append(kwargs)
        return SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))

    monkeypatch.setattr("openai.OpenAI", factory)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    return built


def test_two_calls_with_the_same_key_and_timeout_share_one_client(monkeypatch):
    built = _counting_openai(monkeypatch)
    provider = llm_provider.OpenAIProvider("sk-a")

    provider.chat([{"role": "user", "content": "x"}], timeout=3.0)
    llm_provider.OpenAIProvider("sk-a").chat([{"role": "user", "content": "y"}], timeout=3.0)

    assert len(built) == 1, "a new client per call is a new TCP + TLS handshake per call"


def test_a_different_key_or_timeout_gets_its_own_client(monkeypatch):
    built = _counting_openai(monkeypatch)

    llm_provider.OpenAIProvider("sk-a").chat([{"role": "user", "content": "x"}], timeout=3.0)
    llm_provider.OpenAIProvider("sk-b").chat([{"role": "user", "content": "x"}], timeout=3.0)
    llm_provider.OpenAIProvider("sk-a").chat([{"role": "user", "content": "x"}], timeout=9.0)
    llm_provider.OpenAIProvider("sk-a").chat([{"role": "user", "content": "x"}])

    assert [(b["api_key"], b.get("timeout"), b.get("max_retries")) for b in built] == [
        ("sk-a", 3.0, 0),
        ("sk-b", 3.0, 0),
        ("sk-a", 9.0, 0),
        ("sk-a", None, None),
    ]


def test_a_different_base_url_gets_its_own_client(monkeypatch):
    built = _counting_openai(monkeypatch)

    llm_provider.OpenAIProvider("sk-a").chat([{"role": "user", "content": "x"}], timeout=3.0)
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example.com/v1")
    llm_provider.OpenAIProvider("sk-a").chat([{"role": "user", "content": "x"}], timeout=3.0)

    assert [b.get("base_url") for b in built] == [None, "https://llm.example.com/v1"]


def test_concurrent_first_calls_build_one_client(monkeypatch):
    built = _counting_openai(monkeypatch)
    start = threading.Barrier(8)
    errors: list[BaseException] = []

    def worker():
        try:
            start.wait()
            llm_provider.OpenAIProvider("sk-a").chat([{"role": "user", "content": "x"}], timeout=3.0)
        except BaseException as exc:  # noqa: BLE001 - surfaced by the assert below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(built) == 1


# --------------------------------------------------------------------------- #
# A: a code the code reader read out, and the catalogue does not hold, is not re-read by
# the spec model. Gated on the reader's OWN verdict (`resolutions[i].fallback`, kind
# `code`, matched 0), never on a pattern of our own (owner rule).
# --------------------------------------------------------------------------- #
from app.models.base import set_company_scope  # noqa: E402
from app.models.product import Product  # noqa: E402
from app.services.company_scope import DEFAULT_COMPANY_ID, register_company_scope_listeners  # noqa: E402
from sqlalchemy import text  # noqa: E402

from tests._pg_fixture import unique_code  # noqa: E402

HELD = "ZZTWT5608"
DEAD = "ZZTNOPE1001-BK"


@pytest.fixture
def catalogue():
    register_company_scope_listeners()
    with blank_session() as session:
        current = session.execute(text("SHOW search_path")).scalar()
        session.execute(text(f"SET LOCAL search_path TO {current}, public"))
        set_company_scope(session, None)
        cat, uom = str(uuid.uuid4()), str(uuid.uuid4())
        session.add(ProductCategory(id=cat, category_code=unique_code("C")[:50], category_name="C"))
        session.add(UnitOfMeasure(id=uom, uom_code=unique_code("U")[:20], uom_name="Each"))
        session.flush()
        session.add(
            Product(
                id=str(uuid.uuid4()), product_code=HELD, product_name="Basin mixer chrome", category_id=cat,
                base_uom_id=uom, list_price=10, is_active=True, company_id=DEFAULT_COMPANY_ID,
            )
        )
        session.commit()
        backfill_category_signals(session)
        seed_spec_registry(session)
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
        yield session


class _Reader:
    """A `CodeReader` answering every asked token with one fixed verdict; counts calls."""

    def __init__(self, kind: str, value: str | None):
        self.kind, self.value, self.calls = kind, value, 0

    def __call__(self, missed):
        from app.services.resolver_code_reader import CodeReading

        self.calls += 1
        return {tok: CodeReading(self.kind, self.value) for tok, _typed in missed}


def _ask(
    db, monkeypatch, reader: _Reader, *, query: str, token, raw, match_mode: str = "or"
) -> tuple[dict, list]:
    """The chatbot's resolve request shape (`resolve_gate`: spec_fallback + understand_phrase),
    with the code reader and the spec model both stubbed and counted."""
    from app.api.v1.system import references
    from app.services import resolver_code_reader

    spec_calls: list[dict] = []

    def chat(*_a, **kwargs):
        spec_calls.append(kwargs)
        return SimpleNamespace(content=json.dumps({"specs": []}), prompt_tokens=1, completion_tokens=1, total_tokens=2)

    monkeypatch.setattr(resolver_code_reader, "reader_for", lambda *_a, **_k: reader)
    monkeypatch.setattr(
        understanding, "_resolve_provider", lambda db: (SimpleNamespace(chat=chat), "openai", "gpt-test")
    )
    payload = references.ResolveReferenceRequest(
        query=query,
        tokens=token if isinstance(token, list) else [token],
        raw_tokens=raw if isinstance(raw, list) else [raw],
        allowed_entity_types=["product"],
        fallback_to_all_types=True, spec_fallback=True, understand_phrase=True,
        exact_match=True, limit=50, dry_run=True, domain="inventory", match_mode=match_mode,
        **({"require": {"stock": True}} if match_mode == "and" else {}),
    )
    return references.resolve_reference_post(payload, current_user={"id": None}, db=db), spec_calls


@pytest.mark.parametrize(
    "match_mode",
    # "and" + require stock takes the counted-set (predicate) branch and never reaches the spec
    # reading: kept as a regression guard on that shape, not as coverage of the gate.
    ["or", pytest.param("and", id="and-predicate-branch-guard")],
)
def test_a_read_out_code_the_catalogue_lacks_makes_one_model_call_not_two(catalogue, monkeypatch, match_mode):
    """The scout's `SRT1001-BK` miss: the reader reads the code, the catalogue has no such
    row, and the spec model reading the same code could only find nothing (sandbox: 13 of
    13 such readings answered nothing)."""
    reader = _Reader("code", DEAD)

    result, spec_calls = _ask(
        catalogue, monkeypatch, reader, query=f"stock for {DEAD}?", token="ZZTNOPE1001BK", raw=DEAD,
        match_mode=match_mode,
    )

    fallback = result["resolutions"][0]["fallback"]
    assert fallback["kind"] == "code" and fallback["matched"] == 0, fallback
    assert reader.calls + len(spec_calls) <= 1, (reader.calls, spec_calls)
    assert result["unresolved_tokens"] == ["ZZTNOPE1001BK"], "still the not-found answer"


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        ("none", None),  # a description: what the spec reading exists for
        ("family", "ZZTNOPE"),  # crew ruling: only `code` skips
        ("error", None),  # the reader never answered: nothing to go on
    ],
)
def test_any_other_reader_verdict_still_gets_the_spec_reading(catalogue, monkeypatch, kind, value):
    reader = _Reader(kind, value)

    _result, spec_calls = _ask(
        catalogue, monkeypatch, reader,
        query="chrome basin mixer zztnope 1.0mm", token="chromebasinmixerzztnope1.0mm",
        raw="chrome basin mixer zztnope 1.0mm",
    )

    assert len(spec_calls) == 1, f"verdict {kind!r} must keep the spec model reading"


def test_a_dead_code_beside_a_found_code_makes_one_model_call_not_two(catalogue, monkeypatch):
    """The scout's "5 hits + 1 miss" shape: the found code is a product row, the dead one is
    the reader's `code` with 0 matched, so nothing is left for the spec model to read."""
    reader = _Reader("code", DEAD)

    result, spec_calls = _ask(
        catalogue, monkeypatch, reader, query=f"stock for {HELD} and {DEAD}?",
        token=[HELD, "ZZTNOPE1001BK"], raw=[HELD, DEAD],
    )

    assert [len(r["matches"]) > 0 for r in result["resolutions"]] == [True, False]
    assert reader.calls + len(spec_calls) <= 1, (reader.calls, spec_calls)


# The gate's shape guards (reviewer kill test): each case has an open token the reader read
# as a dead code, plus one more thing that leaves words for the spec model, so it must NOT skip.
_DEAD_OPEN = {"token": "ZZTNOPE1001BK", "matches": [], "fallback": {"asked": True, "kind": "code", "matched": 0}}


@pytest.mark.parametrize(
    "result",
    [
        pytest.param({"intersection": [], "resolutions": [_DEAD_OPEN]}, id="and-shape"),
        pytest.param(
            {
                "resolutions": [_DEAD_OPEN],
                "token_coverage": [{"coverage": [{"entity_type": "product", "unmatched_words": ["matt"]}]}],
            },
            id="product-words-unanswered",
        ),
        pytest.param(
            {"resolutions": [_DEAD_OPEN, {"token": "basintap", "matches": [{"entity_type": "promotion"}]}]},
            id="token-answered-by-non-product-rows-only",
        ),
    ],
)
def test_the_gate_keeps_the_model_reading_when_more_than_a_dead_code_is_open(result):
    from app.api.v1.system.references import _open_tokens_are_codes_the_catalogue_lacks

    assert _open_tokens_are_codes_the_catalogue_lacks(result) is False


def test_the_gate_skips_only_on_the_readers_dead_code_verdict():
    from app.api.v1.system.references import _open_tokens_are_codes_the_catalogue_lacks

    found = {"token": "ZZTWT5608", "matches": [{"entity_type": "product"}]}
    assert _open_tokens_are_codes_the_catalogue_lacks({"resolutions": [found, _DEAD_OPEN]}) is True


def test_a_forked_child_starts_without_the_parents_clients(monkeypatch):
    import os

    built = _counting_openai(monkeypatch)
    llm_provider.OpenAIProvider("sk-a").chat([{"role": "user", "content": "x"}], timeout=3.0)
    read, write = os.pipe()
    pid = os.fork()
    if pid == 0:  # child
        os.close(read)
        os.write(write, str(len(llm_provider._OPENAI_CLIENTS)).encode())
        os._exit(0)
    os.close(write)
    child_count = int(os.read(read, 16).decode())
    os.waitpid(pid, 0)
    assert len(built) == 1 and child_count == 0
