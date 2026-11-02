"""CONFIRM-PREVIEW-STALE round 2 (crew browser pass, 2 Nov 2026): a tab holding an OLDER saved
decision must not overwrite or delete a NEWER one saved elsewhere.

The client sends `based_on_saved_at` (the `saved_at` of the draft its decision stands on;
`null` when it holds none). The server refuses with 409 `board_line_draft_newer` when the
stored draft was saved after that. A request without the field keeps today's behaviour
(older clients, bulk surfaces that never read a draft).
"""
from __future__ import annotations

from .test_fulfilment_line_draft_route import (  # noqa: F401 - `api` is a fixture
    BASE,
    DECISION,
    _board,
    _contribution,
    _save,
    _world,
    api,
)

NEWER = {**DECISION, "reason": "Saved again in another tab."}


def _put(client, key, decision, **extra):
    return client.put(
        f"{BASE}/fulfilment-planning/lines/{key}/draft", json={"decision": decision, **extra}
    )


def _key(api):
    client, world, core_so, *_ = _world(api)
    return client, _contribution(_board(client, core_so), core_so.so_number)["key"], core_so


def test_a_save_based_on_an_older_draft_is_refused_and_the_newer_one_stays(api):
    client, key, core_so = _key(api)
    first = _save(client, key).json()["saved_at"]
    second = _put(client, key, NEWER, based_on_saved_at=first)
    assert second.status_code == 200, second.text
    # A stale tab still holding the FIRST save tries to write over the second.
    stale = _put(client, key, DECISION, based_on_saved_at=first)
    assert stale.status_code == 409, stale.text
    assert stale.json().get("code") == "board_line_draft_newer"
    kept = _contribution(_board(client, core_so), core_so.so_number)["draft"]
    assert kept["decision"]["reason"] == "Saved again in another tab."


def test_a_save_based_on_the_current_draft_goes_through(api):
    client, key, _core_so = _key(api)
    first = _save(client, key).json()["saved_at"]
    again = _put(client, key, NEWER, based_on_saved_at=first)
    assert again.status_code == 200, again.text


def test_a_save_that_expects_no_draft_is_refused_once_one_exists(api):
    client, key, _core_so = _key(api)
    assert _save(client, key).status_code == 200
    blind = _put(client, key, NEWER, based_on_saved_at=None)
    assert blind.status_code == 409, blind.text


def test_a_save_without_the_field_keeps_last_writer_wins(api):
    client, key, _core_so = _key(api)
    assert _save(client, key).status_code == 200
    assert _put(client, key, NEWER).status_code == 200


def test_an_undo_based_on_an_older_draft_is_refused_and_the_newer_one_stays(api):
    client, key, core_so = _key(api)
    first = _save(client, key).json()["saved_at"]
    assert _put(client, key, NEWER, based_on_saved_at=first).status_code == 200
    stale = client.delete(
        f"{BASE}/fulfilment-planning/lines/{key}/draft", params={"based_on_saved_at": first}
    )
    assert stale.status_code == 409, stale.text
    assert stale.json().get("code") == "board_line_draft_newer"
    assert _contribution(_board(client, core_so), core_so.so_number)["draft"] is not None


def test_an_undo_based_on_the_current_draft_removes_it(api):
    client, key, core_so = _key(api)
    saved = _save(client, key).json()["saved_at"]
    gone = client.delete(
        f"{BASE}/fulfilment-planning/lines/{key}/draft", params={"based_on_saved_at": saved}
    )
    assert gone.status_code == 204, gone.text
    assert _contribution(_board(client, core_so), core_so.so_number)["draft"] is None


def test_an_undo_that_holds_no_draft_is_refused_once_one_exists(api):
    """Review round 2 S1: "Undo all" walks pre-marked keys this tab never saw a draft on. A
    draft saved elsewhere meanwhile must not be wiped by it."""
    client, key, core_so = _key(api)
    assert _save(client, key).status_code == 200
    blind = client.delete(
        f"{BASE}/fulfilment-planning/lines/{key}/draft", params={"based_on_saved_at": "none"}
    )
    assert blind.status_code == 409, blind.text
    assert _contribution(_board(client, core_so), core_so.so_number)["draft"] is not None


def test_an_undo_that_holds_no_draft_on_a_line_with_none_is_still_404(api):
    client, key, _core_so = _key(api)
    gone = client.delete(
        f"{BASE}/fulfilment-planning/lines/{key}/draft", params={"based_on_saved_at": "none"}
    )
    assert gone.status_code == 404, gone.text


def test_a_malformed_based_on_is_a_422_not_a_500(api):
    client, key, _core_so = _key(api)
    assert _save(client, key).status_code == 200
    bad = client.delete(
        f"{BASE}/fulfilment-planning/lines/{key}/draft", params={"based_on_saved_at": "soon"}
    )
    assert bad.status_code == 422, bad.text
