"""OI-WHOLE-SO-CANCEL v2, owner ruling 12 Nov 22:55, red: at HEADER level an OI with a line
waiting for CS reads plain "outstanding" (never a waiting_for_cs header status) and is listed
under state=outstanding; its lines_to_confirm still leaves the waiting row out (R1)."""
from __future__ import annotations

from .test_oi_waiting_for_cs import (  # noqa: F401 - fixtures/helpers reused
    _headers,
    _world,
    env,
)


def _mine(env, w, state):
    return [h for h in _headers(env, state=state) if h["id"] == w.inquiry_id]


def test_ac_v2_h_outstanding_an_oi_whose_only_open_row_waits_reads_outstanding(env):
    from app.models.project_so import ACK_ACKNOWLEDGED

    w = _world(env, "date", ack=ACK_ACKNOWLEDGED)

    listed = _mine(env, w, "outstanding")
    assert len(listed) == 1, "listed under state=outstanding"
    assert listed[0]["status"] == "outstanding", listed[0]
    assert listed[0]["lines_to_confirm"] == 0, "R1: the waiting row is not purchasing's to confirm"
    assert _mine(env, w, "completed") == [], "not under completed"


def test_ac_v2_h_outstanding_no_header_ever_reads_waiting_for_cs(env):
    from app.models.project_so import ACK_ACKNOWLEDGED

    _world(env, "date", ack=ACK_ACKNOWLEDGED)
    _world(env, "header_cancel")
    _world(env)

    assert "waiting_for_cs" not in {h["status"] for h in _headers(env, state="all")}
