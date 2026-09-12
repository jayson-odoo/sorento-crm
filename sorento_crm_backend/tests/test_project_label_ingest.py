"""AutoCount push writes `project_label`/`project_label_source` per PLAN-so-project-label.md
Rule 2 (note) and Rule 3 (`ref`), through the precedence gate in
`app.services.project_label_rules.apply_project_label`.

  AC-I1  a pushed SO whose note is the MAYA ARA RTF sample lands with the delivery label
  AC-I2  a PROJECT note line lands as `note`; a corrected re-push updates it
  AC-I3  `ref` is accepted (no 422); an own-collect note + ref lands as `ref`; a note beats a ref
  AC-I4  an `inquiry`-sourced label is never overwritten by a later note
  AC-I5  no note and no ref leaves an existing label untouched; an identical re-push leaves
         `updated_at` untouched

Substrate: `test_ingest_documents.py`'s own `env` fixture (a blank scratch schema, real
Postgres) - the real ingest endpoint end to end, same way `test_rtf_note_strip.py`'s ingest
case reuses it. The scratch schema is built fresh from the current models each run, so it
already carries `project_label`/`project_label_source` once the model does; a red here
therefore names a genuine gap in the ingest WRITE, not a missing column.
"""
from __future__ import annotations

from sqlalchemy import text

from .test_ingest_documents import INGEST_SO, _so_record, env  # noqa: F401
from .test_rtf_note_strip import _SAMPLE_RTF


def _label(env, source_ref):
    row = env.header("sales_orders", source_ref)
    assert row is not None, "the order must exist before its label can be read"
    return row["project_label"], row["project_label_source"]


class TestNoteAndDeliveryLabels:
    def test_i1_a_delivery_address_note_lands_as_a_delivery_label(self, env):
        record = _so_record(env, internal_note=_SAMPLE_RTF)

        res = env.post(INGEST_SO, [record])

        assert res.status_code == 200, res.text
        assert _label(env, record["source_ref"]) == ("MAYA ARA RESIDENCES", "delivery")

    def test_i2_a_project_note_lands_as_note_and_a_correction_updates_it(self, env):
        record = _so_record(env, internal_note="***PROJECT : TAIGA RESIDENCE")
        env.post(INGEST_SO, [record])
        assert _label(env, record["source_ref"]) == ("TAIGA RESIDENCE", "note")

        res = env.post(
            INGEST_SO,
            [dict(record, internal_note="***PROJECT : TAIGA RESIDENCE BLOCK B")],
        )

        assert res.status_code == 200, res.text
        assert _label(env, record["source_ref"]) == ("TAIGA RESIDENCE BLOCK B", "note")


class TestRefLabel:
    def test_i3a_ref_is_accepted_with_no_422_and_lands_as_a_ref_label(self, env):
        # `_so_record`'s own `ref=` keyword means something else entirely (it overrides
        # `source_ref`), so the canonical `ref` field has to be injected as a plain dict
        # key afterwards rather than passed through `_so_record(..., ref=...)`.
        record = _so_record(env, internal_note="***OWN COLLECT")
        record["ref"] = "THE MET KL"

        res = env.post(INGEST_SO, [record])

        assert res.status_code == 200, res.text
        assert res.json()["records"][0]["outcome"] == "created", res.text
        assert _label(env, record["source_ref"]) == ("THE MET KL", "ref")

    def test_i3b_a_project_note_line_beats_a_ref_on_the_same_push(self, env):
        record = _so_record(env, internal_note="***PROJECT : ZUS COFFEE")
        record["ref"] = "THE MET KL"

        res = env.post(INGEST_SO, [record])

        assert res.status_code == 200, res.text
        assert _label(env, record["source_ref"]) == ("ZUS COFFEE", "note")


class TestPrecedenceAgainstInquiry:
    def test_i4_an_inquiry_sourced_label_is_never_overwritten_by_a_later_note(self, env):
        record = _so_record(env, internal_note="***OWN COLLECT")
        env.post(INGEST_SO, [record])
        header = env.header("sales_orders", record["source_ref"])
        # The Order Inquiry importer's own stamp - set directly since this suite is about
        # the INGEST path, not the importer (see test_project_label_order_inquiry_import.py).
        env.db.execute(
            text(
                "UPDATE sales_orders SET project_label = :label, "
                "project_label_source = 'inquiry' WHERE id = :id"
            ),
            {"label": "BAMBOO RESIDENCE / KUALA LUMPUR", "id": header["id"]},
        )
        env.db.flush()

        res = env.post(
            INGEST_SO,
            [dict(record, internal_note="***PROJECT : SOMETHING ELSE ENTIRELY")],
        )

        assert res.status_code == 200, res.text
        assert _label(env, record["source_ref"]) == (
            "BAMBOO RESIDENCE / KUALA LUMPUR",
            "inquiry",
        )


class TestNoChangeLeavesLabelAndUpdatedAtAlone:
    def test_i5a_no_note_and_no_ref_leaves_an_existing_label_untouched(self, env):
        record = _so_record(env)  # no internal_note, no ref
        env.post(INGEST_SO, [record])
        header = env.header("sales_orders", record["source_ref"])
        env.db.execute(
            text(
                "UPDATE sales_orders SET project_label = :label, "
                "project_label_source = 'inquiry' WHERE id = :id"
            ),
            {"label": "BAMBOO RESIDENCE / KUALA LUMPUR", "id": header["id"]},
        )
        env.db.flush()

        res = env.post(INGEST_SO, [dict(record, status="partial")])

        assert res.status_code == 200, res.text
        assert _label(env, record["source_ref"]) == (
            "BAMBOO RESIDENCE / KUALA LUMPUR",
            "inquiry",
        )

    def test_i5b_an_identical_repush_does_not_change_updated_at(self, env):
        record = _so_record(env, internal_note="***PROJECT : TAIGA RESIDENCE")
        env.post(INGEST_SO, [record])
        before = env.header("sales_orders", record["source_ref"])

        res = env.post(INGEST_SO, [record])

        assert res.status_code == 200, res.text
        after = env.header("sales_orders", record["source_ref"])
        assert after["updated_at"] == before["updated_at"]
