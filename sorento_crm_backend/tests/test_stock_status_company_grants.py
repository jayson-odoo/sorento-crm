"""`GET /inventory/stock-status` with `company_scope=grants`.

The order inquiry stock grid overlays AutoCount's figures from this read. A line can sit at a
bin owned by another company the user is granted (read on stock-detail through the same
flag); with company A active this read listed A's bins only, so that bin showed on hand 0.
`company_scope=grants` widens it to the caller's grants, never beyond them, never for an
integration caller, and puts the active scope back afterwards.

Seeding (company A active, user granted A and B, B's bin with on hand 7) is the stock-detail
file's fixture, shared rather than copied.
"""
from __future__ import annotations

from app.models.base import get_company_scope
from tests.test_stock_detail_company_grants import COMPANY_A, api  # noqa: F401 - shared fixture

URL = "/api/v1/inventory/stock-status"


def _get(api, **extra):  # noqa: F811 - the fixture object, passed in
    return api.c.get(URL, params={"product_id": str(api.product.id), **extra})


def _bin(api, res):  # noqa: F811
    assert res.status_code == 200, res.text
    return [loc for loc in res.json()["locations"] if loc["warehouse_id"] == str(api.bin_b.id)]


def test_grants_lists_a_granted_companys_bin(api):  # noqa: F811
    rows = _bin(api, _get(api, company_scope="grants"))

    assert len(rows) == 1, rows
    assert rows[0]["on_hand"] == 7, rows


def test_without_company_scope_the_other_companys_bin_is_absent(api):  # noqa: F811
    assert _bin(api, _get(api)) == []


def test_grants_never_reaches_a_company_the_user_is_not_granted(api):  # noqa: F811
    api.who["user"] = {"id": api.ungranted, "email": "b@zzt.test", "auth_method": "password"}

    assert _bin(api, _get(api, company_scope="grants")) == []


def test_an_integration_caller_is_not_widened(api):  # noqa: F811
    api.who["user"] = {
        "id": api.granted, "email": "a@zzt.test", "auth_method": "integration_api_key",
    }

    res = api.c.get(
        URL,
        params={"product_id": str(api.product.id), "company_scope": "grants"},
        headers={"X-API-Key": "zzt-fake-key"},
    )

    assert _bin(api, res) == []


def test_an_unknown_company_scope_value_is_refused(api):  # noqa: F811
    res = _get(api, company_scope="everything")

    assert res.status_code == 422, res.text


def test_the_active_scope_is_restored_after_a_grants_read(api):  # noqa: F811
    assert len(_bin(api, _get(api, company_scope="grants"))) == 1

    assert get_company_scope(api.db) == frozenset({COMPANY_A})
