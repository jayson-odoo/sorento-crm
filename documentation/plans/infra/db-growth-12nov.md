# DB growth scout (12 Nov 2026)

Status: in progress (scout, investigation only; no app code, no migration). Lane DB-GROWTH.

Problem: prod Postgres will outgrow the Hostinger VPS disk (node A primary, node B streaming replica; both
hold the full DB). This doc: dev numbers, what writes the big tables, non-table disk users, owner-run prod
commands, options, owner questions.

Sections land as the scout completes.
