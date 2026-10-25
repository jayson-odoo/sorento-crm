"""FULFIL-SO-REMARK review round 1, ingest edges (finding 5)."""
from __future__ import annotations

from .test_ingest_documents import INGEST_SO, _so_line, _so_record, env  # noqa: F401


def _stored(env, record):
    header = env.header("sales_orders", record["source_ref"])
    assert header is not None
    return header, env.so_lines(header["id"])[0]


def test_r5_explicit_null_clears_all_three_but_an_absent_key_keeps_them(env):
    line = _so_line(env, line_remark="keep", section_heading="HEAD")
    record = _so_record(env, ship_info="SPONSORSHIP", lines=[line])
    env.post(INGEST_SO, [record])

    cleared = dict(record, ship_info=None,
                   lines=[dict(line, line_remark=None, section_heading=None)])
    res = env.post(INGEST_SO, [cleared])

    assert res.json()["records"][0]["outcome"] in {"updated", "unchanged"}, res.text
    header, stored = _stored(env, record)
    assert header["ship_info"] is None
    assert stored["line_remark"] is None
    assert stored["section_heading"] is None


def test_r5_over_long_ship_info_and_heading_are_truncated_not_rejected(env):
    line = _so_line(env, section_heading="H" * 1500)
    record = _so_record(env, ship_info="S" * 300, lines=[line])

    res = env.post(INGEST_SO, [record])

    assert res.status_code == 200, res.text
    assert res.json()["records"][0]["outcome"] == "created", res.text
    header, stored = _stored(env, record)
    assert header["ship_info"] == "S" * 255
    assert 0 < len(stored["section_heading"]) <= 255


def test_r5_a_huge_rtf_line_remark_is_cut_and_the_record_accepted(env):
    rtf = "{\\rtf1\\ansi " + ("word " * 100000) + "}"
    assert len(rtf) > 256 * 1024
    record = _so_record(env, lines=[_so_line(env, line_remark=rtf)])

    res = env.post(INGEST_SO, [record])

    assert res.status_code == 200, res.text
    assert res.json()["records"][0]["outcome"] == "created", res.text
    _header, stored = _stored(env, record)
    assert 0 < len(stored["line_remark"]) <= 8000
