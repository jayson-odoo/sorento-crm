"""The 50 MB ceiling, at its real value and against a real oversized body.

S7.3 covered the ceiling by monkeypatching the constant down to a few bytes,
which proves the comparison is wired up and nothing else. Two things it cannot
show, and both are the reason the code is shaped the way it is:

* that the guard still fires at the REAL constant, rather than at a number no
  production upload will ever reach, and
* that the read STOPS EARLY. `_read_within_limit` chunks the upload instead of
  taking one `await file.read()` precisely so an oversized flyer is refused on
  the first megabyte past the limit rather than after the whole thing has been
  assembled in memory. A version that read everything and then compared would
  pass every assertion about the response while doing the opposite of what the
  loop exists for, so the read count is asserted directly.

The real flyer is 20 MB, so 50 MB is headroom rather than a constraint anybody
meets by accident.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.dealer_kit import flyer_reading_service as svc

# Comfortably over the ceiling, and enough past it that a loop which failed to
# stop would be obvious in the read count.
OVERSIZE_BYTES = svc.MAX_UPLOAD_BYTES + (10 * 1024 * 1024)


@pytest.fixture
def as_designer():
    """Authenticated and permitted, so the ceiling is what the test measures.

    Written first as an override on the route module's own `_EDIT` / `_VIEW`
    dependency objects, which does nothing: FastAPI keys the override map on the
    CALLABLE inside `Depends(...)`, so the real resolver ran and every request
    401'd before a single byte was read. The tests then passed or failed on
    authentication rather than on the ceiling. Overriding the underlying
    `get_current_user` family is what actually reaches the route, and it is the
    pattern the rest of this module's tests use.

    The permission checks resolve through the same dependency, so a principal
    supplied here is treated as permitted.
    """
    from app.api.v1.dealer_kit import flyer_readings as routes
    from app.dependencies import get_current_user, get_current_user_or_api_key

    principal = {"id": str(uuid.uuid4()), "email": "zzt-designer@example.com"}
    # BOTH layers. The router carries a module guard that resolves the principal
    # (401 without this), and the route carries the permission check (403 without
    # the second pair). Overriding either alone stops the request before it ever
    # reads a byte, which is the whole subject of these tests.
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
    app.dependency_overrides[routes._EDIT] = lambda: principal
    app.dependency_overrides[routes._VIEW] = lambda: principal
    yield principal
    app.dependency_overrides.clear()


def test_the_ceiling_fires_at_its_real_value_and_names_the_limit(as_designer) -> None:
    """No monkeypatched constant: the number a real upload is measured against."""
    body = b"%PDF-1.4\n" + (b"0" * (OVERSIZE_BYTES - 9))
    assert len(body) > svc.MAX_UPLOAD_BYTES

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/dealer-kit/flyer-readings",
            files={"file": ("zzt-huge.pdf", body, "application/pdf")},
        )

    assert response.status_code in (400, 413), response.text
    # The limit has to be IN the message. "Too large" without a number leaves
    # somebody guessing how much to cut, and they will guess wrong.
    assert "50" in response.text


def test_the_read_stops_at_the_ceiling_rather_than_swallowing_the_file(
    as_designer, monkeypatch
) -> None:
    """The chunk loop's whole reason for existing, pinned.

    Counts the reads rather than the response: a rewrite that took one
    `await file.read()` and compared afterwards would answer 400 exactly as this
    one does, while holding the entire oversized upload in memory first. That is
    the regression this test is here to catch, and it is invisible from outside.
    """
    from app.api.v1.dealer_kit import flyer_readings as routes

    # Spying on the GUARD rather than on `UploadFile.read`. Patching the class
    # the route imported records nothing, because the object Starlette hands the
    # endpoint is not that class, so the spy silently never fires and the test
    # passes on an empty list. The guard is called once per chunk by the loop
    # itself, which measures the same thing and cannot be missed the same way.
    seen: list[int] = []
    original = svc.assert_within_limit

    def spying_guard(total: int):
        seen.append(total)
        return original(total)

    monkeypatch.setattr(svc, "assert_within_limit", spying_guard)
    monkeypatch.setattr(routes.svc, "assert_within_limit", spying_guard)

    body = b"%PDF-1.4\n" + (b"0" * (OVERSIZE_BYTES - 9))

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/dealer-kit/flyer-readings",
            files={"file": ("zzt-huge.pdf", body, "application/pdf")},
        )

    assert response.status_code in (400, 413), response.text

    # Called more than once, with a growing running total: that IS the chunked
    # read. A rewrite taking one `await file.read()` would call the guard exactly
    # once, with the whole file already in memory.
    assert len(seen) > 1, f"the guard ran {len(seen)} time(s), so nothing was chunked"
    assert seen == sorted(seen)

    consumed = seen[-1]
    # One chunk past the limit is the design: the guard runs AFTER each read, so
    # the read that crosses the ceiling has already happened. Anything beyond
    # that means the loop kept going.
    ceiling_with_one_chunk = svc.MAX_UPLOAD_BYTES + routes._CHUNK_BYTES
    assert consumed <= ceiling_with_one_chunk, (
        f"read {consumed} bytes of a {len(body)} byte upload; the loop should "
        f"have stopped by {ceiling_with_one_chunk}"
    )
    # And it did have to read most of the way there, or the assertion above
    # would also hold for a route that read nothing at all.
    assert consumed > svc.MAX_UPLOAD_BYTES
