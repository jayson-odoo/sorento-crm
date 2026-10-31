# PLAN: user guides <-> Outline sync, automatic both ways

Status: in progress (small fix track: CI/tooling only, no app change, no migration)

## Why

Owner, 31 Oct 2026: "make the mechanism consistent and autonomous". Until now the pull
(Outline -> repo) ran every 6h but the push (repo -> Outline) only ran by hand, and the first
manual push (run 41178406314) died part-way on a page title over Outline's 100-character limit.

## Changes

1. `outline-user-guides-sync.yml` pushes on every push to main touching
   `documentation/user-guides/**` (state file excluded), one concurrency group for push and pull.
2. Pull and push PRs go to one bot branch, labelled `docs-sync`; the push commits the doc-id state
   it learnt, and pull re-learns ids by title so a missed state commit never duplicates a page.
3. `sync_user_guides_outline.py check` (stdlib only, no network) runs in the PR gate: fails on a
   guide folder in neither `PARENT_TITLES` nor `HELD_FOLDERS`, an unexpected layout, or a title
   over 100 characters.
4. Push continues past a failing page and fails at the end with every failure listed.
5. `project-sales-rep/submit-via-portal.md` title shortened (111 -> under 100).
6. SYNC.md describes the automatic flow.
