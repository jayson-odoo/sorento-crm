# PLAN: user guides refresh for merges since 17 Oct

Status: in progress (small fix track, docs only: no code, no migration, no auth change)

Lane: DOCS-REFRESH

## Why

The in-app AI assistant answers "how do I" questions from the user guides
(`documentation/user-guides/`, mirrored to Outline and read through MCP `user_guides_read`).
The guides were last refreshed on 17 Oct (#1748). Since then roughly 50 merges changed
user-visible behaviour, so the assistant answers some questions from stale pages. Owner goal
(31 Oct): a staff member who does not know the system asks the assistant panel and understands
the answer without contacting the owner.

## Scope

1. Map every user-visible merge since 17 Oct to an existing guide page or "missing"
   (table below, filled in as the lane progresses).
2. Update or add guide pages, following `documentation/user-guides/README.md` conventions
   (H1 title, one-line summary, Steps with verbatim UI labels in bold, what gets created,
   how you are notified, See also) and register new pages in `.outline-sync.json` only through
   the sync script (new pages get their Outline id on the next push; no hand-made ids).
3. Before writing: check the Outline -> repo sync branch so Outline-side edits are not
   overwritten.
4. Do not dispatch the repo -> Outline push. The owner runs it after merge.

## Outline sync check (31 Oct)

`origin/bot/outline-user-guides-sync` (406ab415, 31 Oct 03:39 UTC) has no open PR. It adds
`docs/user-guides/README.md` + `.outline-sync.json` (a `docs/` path, not `documentation/`),
and its Overview body is an OLDER copy of the repo README (the repo has the later wording).
So no Outline-side edit is newer than the repo and nothing needs merging. The path mismatch is
reported to the owner separately: `scripts/sync_user_guides_outline.py:46` sets
`GUIDES_DIR = REPO_ROOT / "docs" / "user-guides"` and the workflow's `add-paths` is
`docs/user-guides/**`, while the guides live under `documentation/user-guides/`.

## Feature map

(filled in below)

## UAC

See `user-guides-refresh-acceptance-criteria.md`.
