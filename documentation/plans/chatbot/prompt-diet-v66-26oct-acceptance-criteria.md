# UAC: PROMPT-DIET-V66

Plan: `PLAN-prompt-diet-v66-26oct.md`.

- AC1: `chatbot_prompt_diet_edits.build` on the exact prod v66 text (md5 fb7b4283) returns a text (not None); every
  anchor is found exactly once in turn.
- AC2: `build` on v185 (the #1867 base, md5 3f1e2d27) returns the same bytes as before this lane (md5 94fccf45,
  102,402 chars).
- AC3: the v66 diet text keeps the owner's v66 edit: no `one <customer name>` in it.
- AC4 (dropped, scope change: no migration): migration `diet_0002_parser_diet_v66` on a production-labelled base that takes the edits inserts exactly one new
  version, unlabelled, with the built template; the production label still points at the old version.
- AC5 (dropped with AC4): on a base that does not take the edits it inserts nothing, logs a warning, and the upgrade still succeeds.
- AC6 (dropped with AC4): a second run inserts nothing (idempotent); on a base whose diet text diet_0001 already published (dev, v63) it
  inserts nothing.
- AC7 (dropped with AC4): downgrade deletes only the unlabelled versions carrying diet_0002's own commit message.
- AC8 (dropped with AC4): single alembic head after the migration.
- AC9: parser gold gate: arm B (v66 diet) not worse than arm A (v66) beyond the #1867 accepted noise (TRAIN within 1).
- AC10: the diet text, its md5 + char count and a section change summary vs v66 are in crew/state/outbox/diet-v66/.
