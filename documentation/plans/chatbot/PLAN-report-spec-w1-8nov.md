# PLAN: REPORT-SPEC-W1, golden corpus + harness (8 Nov 2026)

Status: in progress, the corpus is green on main. Pending crew: the held lines for the 156 turns (being extracted), and the step-18 re-run x3 (live agent turns, after the dev agent daily cap resets). UAC:
`report-spec-w1-acceptance-criteria.md`. Track: small fix (tests + data only, no app change, no migration, no auth/RBAC, no screen).

Source: `ARCH-report-engine-7nov.md` sections 3.0 and 3.2 (W1) and 3.2.1 (re-record runbook).

## Scope

1. `sorento_crm_backend/tests/chatbot/golden/report_turns.jsonl`: the L1 corpus, one row per recorded live turn.
   Keys: `head`, `run`, `step`, `turn_id`, `text`, `held`, `held_spec`, `report_ask`, `open_question`, `expect`
   (`route_params` | `ask_field` | `refusal`), `role` (`expectation` | `seed`), `prompt_md5`, optional `xfail`.
2. `sorento_crm_backend/tests/chatbot/test_report_golden.py`: one parametrized pytest running every row in order
   through the real engine with recorded parses (no LLM).
3. A `held` key on every row of `scripts/chatbot_eval/gold/parser_report_{semantic_carry,totals_filters,v92,filter_all}.jsonl`.
4. Gold rows whose expected params can be read off existing tests become L1 rows.

Out of scope: anything under `app/`, prompt edits, deleting rules or tests, `golden/chat_report_golden.json`.

## Acceptance (the first red tests)

1. `test_corpus_file_has_every_expectation_turn`: 78 expectation rows (4c1b310a) + 3 step-18 rows, unique keys.
2. `test_every_row_carries_its_held_line`: every row has `held`; a non-null value starts `Held report` and parses
   as JSON after the colon.
3. `test_engine_prints_the_recorded_held_line[row]`: the engine's held line after replaying the run so far equals
   the recorded one.
4. `test_report_golden[row]`: route params / ask field / refusal equal `expect`; 4c1b310a step 11 is `xfail`
   (`REPORT-SPEC-W3`).
5. `test_seed_rows_are_never_expectations`: 2a8e6f7c rows are counted and skipped.

Rules kept: semantic only (no regex/keyword rules), rule freeze, one engine (route params shape shared with the
agent), prompts pinned by md5.
