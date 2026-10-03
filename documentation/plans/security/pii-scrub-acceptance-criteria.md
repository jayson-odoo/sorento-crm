# UAC: PII scrub of the public repo (PII-SCRUB)

Plan: [PLAN-pii-scrub.md](PLAN-pii-scrub.md)

- **AC-1** `python3 scripts/pii_guard.py` on `main` HEAD prints `pii-guard: clean` and exits 0.
- **AC-2** No Respond.io contact id that exists in the dev DB appears in any tracked file or path,
  including inside a fixture `phone` built from the id.
- **AC-3** No real MY mobile number appears in any tracked file in any of these shapes: `+60`,
  `60`, `0060`, `%2B60`, `0`, `(01x)`, with spaces or dashes, after a letter or underscore, or
  inside an Office file.
- **AC-4** Every value under a `phone`, `wa_id`, `contact_phone*` or `mobile*` key is a fake shape.
- **AC-5** No labelled lorry plate (Lorry Plate, lorry_plate, Lorry No, car/vehicle/truck plate or
  no, No Plat, No Kenderaan, a `plate` key) holds anything but `PLATE-N`.
- **AC-6** No `.playwright-mcp/`, `*.har` or `*.rdb` path is tracked, and `.gitignore` covers them.
- **AC-7** The guard's output never contains the matched value.
- **AC-8** Replay fixtures stay self-consistent: the chatbot replay and node-fixture suites pass
  with the same results as `main` (pre-existing corpus failures excepted).
- **AC-9** No behaviour change: app-code edits are docstrings, examples and sample data, except
  two dev-only seeds (migration 183's optional dev-user link and `seed_project_cs_demo.py`'s demo
  owner), which now name a fake email and so fall back.
- **AC-10** The `pii-guard` job runs on every `ci`-labelled PR and on pushes to `main`, beside the
  alembic gate; the pre-push hook runs the same script.
