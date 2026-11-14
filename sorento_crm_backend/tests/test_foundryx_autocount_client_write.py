"""AC-QTSO-CRM Phase 2, RED: `FoundryxAutocountClient.write_capabilities / write / patch`.

Plan, "Client": `write_capabilities(company_code)` and `write(path, body, *, idempotency_key)`
copied verbatim from #2168, plus `patch(path, body, *, idempotency_key)` with the same answer rule:

* a body carrying `outcome` is returned as-is for ANY status (409, 422, 502 ...), so the caller
  shows what AutoCount said;
* anything else goes through `_parse` (401/403/404 -> NOT_CONFIGURED 502; other errors keep the
  gateway's code);
* a transport error raises `FoundryxPullError` code UNREACHABLE.

The key rides the `Idempotency-Key` header and the API key `X-API-Key`; `write` POSTs and `patch`
PATCHes under `/api/v1/autocount/`.
"""
from __future__ import annotations

import httpx
import pytest

from tests._pg_fixture import blank_session
from tests._ac_write_support import (
    CAPS_PATH,
    FakeSS,
    SS_API_KEY,
    SS_BASE_URL,
    done_body,
    refused_body,
)
from tests.support.fake_foundryx import seed_foundryx_connection

DOC = "/api/v1/autocount/documents/sales-orders"


@pytest.fixture
def fake(monkeypatch) -> FakeSS:
    from app.services import foundryx_autocount_client as client_mod

    f = FakeSS()
    monkeypatch.setattr(client_mod, "TRANSPORT", httpx.MockTransport(f.handler), raising=False)
    return f


@pytest.fixture
def client(fake):
    from app.services.foundryx_autocount_client import FoundryxAutocountClient

    with blank_session() as db:
        seed_foundryx_connection(db, base_url=SS_BASE_URL, api_key=SS_API_KEY)
        db.flush()
        yield FoundryxAutocountClient(db)


def test_write_capabilities_reads_the_feed_with_the_company_code(client, fake):
    answer = client.write_capabilities("SRT")

    assert "capabilities" in answer
    [request] = fake.calls
    assert request.method == "GET" and request.url.path == CAPS_PATH
    assert request.url.params["companyCode"] == "SRT"
    assert request.headers["X-API-Key"] == SS_API_KEY


def test_write_posts_the_body_with_the_idempotency_key(client, fake):
    fake.answers[("POST", DOC)] = (200, done_body())

    answer = client.write("documents/sales-orders", {"companyCode": "SRT"}, idempotency_key="k-1")

    assert answer["outcome"] == "done"
    [request] = fake.calls
    assert request.method == "POST" and request.url.path == DOC
    assert request.headers["Idempotency-Key"] == "k-1"
    assert request.headers["X-API-Key"] == SS_API_KEY
    assert fake.body(request) == {"companyCode": "SRT"}


def test_patch_sends_a_patch_with_the_idempotency_key(client, fake):
    fake.answers[("PATCH", f"{DOC}/12008")] = (200, done_body())

    answer = client.patch("documents/sales-orders/12008", {"companyCode": "SRT"}, idempotency_key="k-2")

    assert answer["outcome"] == "done"
    [request] = fake.calls
    assert request.method == "PATCH" and request.url.path == f"{DOC}/12008"
    assert request.headers["Idempotency-Key"] == "k-2"
    assert fake.body(request) == {"companyCode": "SRT"}


@pytest.mark.parametrize("status", [409, 422, 502])
@pytest.mark.parametrize("verb", ["write", "patch"])
def test_an_outcome_body_is_returned_as_is_for_an_error_status(client, fake, verb, status):
    body = refused_body("DOC_STALE", "changed since expectedLastModified")
    method = "POST" if verb == "write" else "PATCH"
    fake.answers[(method, f"{DOC}/12008")] = (status, body)

    answer = getattr(client, verb)("documents/sales-orders/12008", {}, idempotency_key="k")

    assert answer == body


def test_a_202_pending_outcome_is_returned_as_is(client, fake):
    body = {**done_body(), "outcome": "pending_verification"}
    fake.answers[("POST", DOC)] = (202, body)

    assert client.write("documents/sales-orders", {}, idempotency_key="k") == body


@pytest.mark.parametrize("verb", ["write", "patch"])
def test_a_flat_error_body_goes_through_the_ordinary_error_path(client, fake, verb):
    from app.services.foundryx_autocount_client import FoundryxPullError

    method = "POST" if verb == "write" else "PATCH"
    fake.answers[(method, DOC)] = (400, {"code": "BAD_REQUEST", "message": "missing header"})

    with pytest.raises(FoundryxPullError) as caught:
        getattr(client, verb)("documents/sales-orders", {}, idempotency_key="k")

    assert caught.value.code == "BAD_REQUEST"
    assert caught.value.status == 400


@pytest.mark.parametrize("verb", ["write", "patch"])
def test_a_rejected_key_is_not_configured_never_an_outcome(client, fake, verb):
    from app.services.foundryx_autocount_client import FoundryxPullError

    method = "POST" if verb == "write" else "PATCH"
    fake.answers[(method, DOC)] = (401, {"code": "UNAUTHORIZED", "message": "bad key"})

    with pytest.raises(FoundryxPullError) as caught:
        getattr(client, verb)("documents/sales-orders", {}, idempotency_key="k")

    assert caught.value.code == "NOT_CONFIGURED"
    assert caught.value.status == 502


@pytest.mark.parametrize("verb", ["write", "patch"])
def test_a_transport_error_is_unreachable(client, fake, verb):
    from app.services.foundryx_autocount_client import FoundryxPullError

    fake.transport_error = httpx.ConnectError("down")

    with pytest.raises(FoundryxPullError) as caught:
        getattr(client, verb)("documents/sales-orders", {}, idempotency_key="k")

    assert caught.value.code == "UNREACHABLE"
    assert caught.value.status == 502


def test_a_timeout_is_unreachable_too(client, fake):
    from app.services.foundryx_autocount_client import FoundryxPullError

    fake.transport_error = httpx.ReadTimeout("slow")

    with pytest.raises(FoundryxPullError) as caught:
        client.patch("documents/sales-orders/1", {}, idempotency_key="k")

    assert caught.value.code == "UNREACHABLE"
