# UAC: REPORT-SPEC-W1, golden corpus + harness

Plan: `PLAN-report-spec-w1-8nov.md`. Source: `ARCH-report-engine-7nov.md` 3.0, 3.2 (W1), 3.2.1.

- W1-1: `tests/chatbot/golden/report_turns.jsonl` holds the 78 turns of 4c1b310a as expectation rows, the 9 step-18
  re-run rows (x3 on 289da7e5) as expectation rows (pending crew, dev cap), and the 78 turns of 2a8e6f7c as seed rows; keys
  (head, run, step, turn_id) are unique.
- W1-2: every row has `held`; a non-null value is one line starting `Held report`, and its JSON equals `held_spec`.
- W1-3: for every expectation row with a recorded `held`, the engine prints that same line when the run is replayed
  up to the row.
- W1-4: every expectation row's route params (in names), ask field or refusal equals its `expect`. A known miss is a
  strict `xfail` tagged `REPORT-SPEC-W3` or `REPORT-SPEC-W4`; 4c1b310a step 11 is one (PARSER_MISS, company).
- W1-5: seed rows carry `expect: null` and are never asserted.
- W1-6: every row names the md5 of a pinned prompt text; the pinned texts are unchanged.
- W1-7: every L0 gold row of `parser_report_{semantic_carry,totals_filters,v92,filter_all}.jsonl` has a `held` key.
- W1-8: no file under `sorento_crm_backend/app/` changes; `test_report_filter_all_live.py` still passes.
