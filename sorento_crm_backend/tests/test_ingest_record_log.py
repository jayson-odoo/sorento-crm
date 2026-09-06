"""Fix round 6 - one INFO log line per failed/retryable record.

Live need from the ESB: a record stayed retryable across 4 pushes and the
server log only ever had the batch summary line (`ingest.batch ...
retryable=1`), with no way to tell WHICH record or WHY without reproducing
the push. `app/api/v1/external/ingest.py::_log_record_outcomes` adds one
`ingest.record` line per failed/retryable record, right where the batch
summary is already logged, capped at 50 lines then one `ingest.record_overflow`
line.

No new substrate - reuses `env` from `tests.test_ingest_documents`.
"""
from __future__ import annotations

import logging

from tests.test_ingest_documents import (
    INGEST_SO,
    _so_record,
    env,  # noqa: F401 - pytest fixture, imported for reuse
)

__all__ = ["env"]

_LOGGER_NAME = "app.api.v1.external.ingest"


def _record_lines(caplog):
    return [
        r.getMessage() for r in caplog.records if r.getMessage().startswith("ingest.record ")
    ]


class TestRetryableRecordIsLogged:
    def test_a_retryable_record_logs_exactly_one_ingest_record_line(self, env, caplog):
        caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
        record = _so_record(env, customer_ref="DEBTOR:NOT-SYNCED-YET")

        res = env.post(INGEST_SO, [record])

        assert res.json()["records"][0]["outcome"] == "retryable", res.text
        lines = _record_lines(caplog)
        assert len(lines) == 1, lines
        line = lines[0]
        assert record["source_ref"] in line
        assert "outcome=retryable" in line
        assert "customer_ref" in line
        assert "entity=sales_orders" in line

    def test_a_clean_created_batch_logs_no_record_lines(self, env, caplog):
        caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
        record = _so_record(env)

        res = env.post(INGEST_SO, [record])

        assert res.json()["records"][0]["outcome"] == "created", res.text
        assert _record_lines(caplog) == []

    def test_a_dry_run_logs_no_record_lines_even_for_a_retryable_record(self, env, caplog):
        caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
        record = _so_record(env, customer_ref="DEBTOR:NOT-SYNCED-YET")

        res = env.post(INGEST_SO, [record], dry_run=True)

        assert res.json()["records"][0]["outcome"] == "retryable", res.text
        assert _record_lines(caplog) == []
