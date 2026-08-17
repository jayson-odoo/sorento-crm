"""Drill-down tools follow the same serving rule as the list (captain, 2026-08-16).

The list tools hand the agent expired-but-usable promotions ("ended on 31/07 but
still applies"). The drill-down tools used to block anything with
`is_active=false`, so the very next call about the promotion it had just quoted
came back "Promotion is inactive." - one surface, two answers.

The backend stamps `expired_but_usable` from the single serving policy, so the
filter now asks that instead of asking about the raw active flag. An expired
special (which the policy withholds) is still blocked.

Run: pytest tests/test_promotion_drilldown_serving.py -v
"""
from __future__ import annotations

import json

from sorento_crm_mcp.server import _filter_active_promotion_records, _is_active_promotion_obj

_GET = "crm_marketing_promotions_get"
_BY_PROMOTION = "crm_marketing_promotion_attachments_by_promotion"


def test_live_promotion_is_drillable():
    assert _is_active_promotion_obj({"is_active": True, "description": "live"}) is True


def test_expired_but_usable_promotion_is_drillable():
    """The whole point: the list served it, so the detail must open it."""
    assert (
        _is_active_promotion_obj(
            {"is_active": False, "expired_but_usable": True, "description": "july wc promo"}
        )
        is True
    )


def test_expired_and_withheld_promotion_stays_blocked():
    """An expired special carries expired_but_usable=false and stays blocked."""
    assert (
        _is_active_promotion_obj(
            {"is_active": False, "expired_but_usable": False, "description": "special"}
        )
        is False
    )


def test_get_returns_the_expired_but_usable_record():
    raw = json.dumps(
        {
            "id": "p1",
            "description": "JULY SORENTO WC PROMO",
            "is_active": False,
            "expired_but_usable": True,
            "promotion_type_code": "pp",
        }
    )
    out = _filter_active_promotion_records(_GET, raw)
    assert json.loads(out)["promotion_type_code"] == "pp"


def test_get_still_blocks_a_withheld_expired_promotion():
    raw = json.dumps(
        {
            "id": "p2",
            "description": "SORENTO SPECIAL PROMO",
            "is_active": False,
            "expired_but_usable": False,
        }
    )
    out = json.loads(_filter_active_promotion_records(_GET, raw))
    assert out["code"] == "PROMOTION_INACTIVE"


def test_child_rows_of_an_expired_but_usable_promotion_survive():
    """Attachments of a served-but-expired promotion are reachable too."""
    raw = json.dumps(
        {
            "data": [
                {
                    "id": "a1",
                    "promotion": {
                        "id": "p1",
                        "is_active": False,
                        "expired_but_usable": True,
                    },
                },
                {
                    "id": "a2",
                    "promotion": {
                        "id": "p2",
                        "is_active": False,
                        "expired_but_usable": False,
                    },
                },
            ]
        }
    )
    rows = json.loads(_filter_active_promotion_records(_BY_PROMOTION, raw))["data"]
    assert [row["id"] for row in rows] == ["a1"]
