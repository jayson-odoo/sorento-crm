"""OCN-ORDER-CHANGE-NOTICE round 17b (security round 4, L7): the notice's customer lookup cannot
page the whole customer list. Like the portal debtor lookup: at most 50 rows, a search of at
least 2 characters (shorter or empty: no rows, not an error), a search of at most 100 characters
(longer: 422).

Postgres only, every row seeded.
"""
from __future__ import annotations

import uuid

from ._forms_chain_support import world  # noqa: F401
from ._ocn_support import OCN, customer, ocn  # noqa: F401  (fixture)

LOOKUP = f"{OCN}/lookups/customers"


def test_r17b_an_empty_or_one_character_search_lists_no_one(ocn):
    customer(ocn.db, name=f"ZZT {uuid.uuid4().hex[:6]} Anyone")
    ocn.db.commit()
    for q in ("", "Z", " Z "):
        res = ocn.as_(ocn.own).get(LOOKUP, params={"q": q})
        assert res.status_code == 200, (q, res.text)
        assert res.json() == [], q


def test_r17b_more_than_fifty_rows_is_refused(ocn):
    assert ocn.as_(ocn.own).get(LOOKUP, params={"q": "ZZT", "limit": 1000}).status_code == 422
    assert ocn.as_(ocn.own).get(LOOKUP, params={"q": "ZZT", "limit": 51}).status_code == 422


def test_r17b_fifty_rows_at_most(ocn):
    tag = uuid.uuid4().hex[:6].upper()
    for i in range(55):
        customer(ocn.db, name=f"ZZT {tag} {i:02d}")
    ocn.db.commit()
    res = ocn.as_(ocn.own).get(LOOKUP, params={"q": tag, "limit": 50})
    assert res.status_code == 200, res.text
    assert len(res.json()) == 50


def test_r17b_a_search_over_a_hundred_characters_is_refused(ocn):
    assert ocn.as_(ocn.own).get(LOOKUP, params={"q": "x" * 101}).status_code == 422
    assert ocn.as_(ocn.own).get(LOOKUP, params={"q": "x" * 100}).status_code == 200
