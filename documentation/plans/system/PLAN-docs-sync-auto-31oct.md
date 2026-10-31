# PLAN: user guides <-> Outline sync, automatic both ways

Status: in review, PR #2043 (small fix track: CI/tooling only, no app change, no migration, no auth; the diff is ~600 lines, mostly tests and SYNC.md)

## Why

Owner, 31 Oct 2026: "make the mechanism consistent and autonomous". Until now the pull
(Outline -> repo) ran every 6h but the push (repo -> Outline) only ran by hand, and the first
manual push (run 41178406314) died part-way on a page title over Outline's 100-character limit.

## Changes

1. `outline-user-guides-sync.yml` pushes on every push to main touching
   `documentation/user-guides/**` (state file excluded), one concurrency group for push and pull.
2. The pull PR (one bot branch) is labelled `docs-sync`. The push opens no PR: the next pull learns
   the ids of docs the push created by title, so a doc never comes back as a duplicate slug page.
   Push keeps an Outline page a person edited after the repo commit (`outline_is_newer`, the
   mirror of pull's `repo_is_newer`) and skips pages already the same.
3. `sync_user_guides_outline.py check` (stdlib only, no network) runs in the PR gate: fails on a
   guide folder in neither `PARENT_TITLES` nor `HELD_FOLDERS`, an unexpected layout, or a title
   over 100 characters.
4. Push continues past a failing page and fails at the end with every failure listed.
5. `project-sales-rep/submit-via-portal.md` title shortened (111 -> under 100).
6. SYNC.md describes the automatic flow.
