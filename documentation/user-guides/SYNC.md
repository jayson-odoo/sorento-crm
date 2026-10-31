# User-guides ↔ Outline two-way sync

The user guides under `documentation/user-guides/` are mirrored to the **Sorento CRM** collection on Outline (`https://doc.foundryx.my/collection/sorento-crm-BOoUtlxxTH`). MCP tools, the in-app footer "Docs" link, and the n8n / WhatsApp agent all read from Outline at runtime, so Outline is the user-facing source of truth.

The repo copy is kept in sync so that:

- Engineering can review documentation changes in PRs.
- Outline outages don't break local AI tooling (the markdown is still on disk).
- Edits made by non-engineers in Outline land back in git automatically.

## How it runs (automatic, both directions)

Nobody runs the sync by hand any more. `.github/workflows/outline-user-guides-sync.yml`:

| Direction | When | What it does |
|---|---|---|
| **push** (repo -> Outline) | every push to `main` that changes `documentation/user-guides/**` (the state file alone does not count) or the sync script | `dry-run` first (validates, no token, no network), then `push` |
| **pull** (Outline -> repo) | every 6 hours | `pull`, then opens or refreshes ONE PR on `bot/outline-user-guides-sync`, labelled `docs-sync` |

Both share one concurrency group (`outline-user-guides-sync`), so two pushes never overlap and a
pull never runs while a push is writing. A running sync is never cancelled, but GitHub keeps only
ONE queued run per group: a newer queued run (push or pull) replaces the older one. A push replaced
by a push loses nothing (every run checks out `main`'s current head). A push replaced by the
6-hourly pull is lost until the next guide merge pushes again, or dispatch `mode=push` by hand. The
pull can not undo it meanwhile: it never pulls a page last written by the sync's own push.

So the loop is: merge a guide PR -> it is on Outline a minute later. Edit on Outline -> within 6h a
`docs-sync` PR brings it back -> merge it (its push finds those pages already the same).

Neither side overwrites the other's newer edit:

- **pull** keeps a repo page whose last commit is newer than its Outline copy (`repo_is_newer`,
  prints `[keep] ... (repo copy is newer than Outline's, push it)`).
- **push** keeps an Outline page a person edited after the repo page's last commit
  (`outline_is_newer`, prints `[keep] ... (Outline copy edited after the repo commit, pull it)`).
  Edits made by the sync's own API user (an earlier push) do not count, and pull likewise never
  pulls a page that user last wrote. **So the token must belong to a dedicated Outline account
  nobody edits guides as**: with a person's token, that person's Outline edits would read as the
  sync's own and the next push would overwrite them. To overwrite anyway,
  dispatch the workflow with `mode=push` and `force` ticked (`OUTLINE_SYNC_FORCE=1` locally).
- push skips a page whose title and text already match (`[same]`).

A page edited on both sides keeps whichever side the guard protects; re-apply the other edit by hand.

A push that fails on one page carries on with the rest, saves the ids it learnt, then exits red with
every failure listed (`N page(s) FAILED to push`), so one bad page never stops the others.

### PR gate: `check`

`python3 scripts/sync_user_guides_outline.py check` runs in the PR gate (`deploy.yml`
`lean-gate`, step "User guides publish to Outline"; stdlib only, no network). It fails the PR when:

- a guide folder is in neither `PARENT_TITLES` nor `HELD_FOLDERS` (its pages would be skipped as
  `unknown folder` and never reach Outline or the AI assistant);
- a markdown file sits outside the `<folder>/<page>.md` layout;
- a page H1, parent or root title is over Outline's 100-character limit (`MAX_TITLE_LEN`; Outline
  answers 400 "Document title must be 100 characters or less").

Run it locally before pushing a guide change.

### Doc ids (`.outline-sync.json`)

The push runs on a runner and does not commit the state file. The next pull learns the ids of
docs the push created by matching titles (parents against `PARENT_TITLES`, pages against the H1
of the repo page in the same folder; `[learn]` in the log), and its `docs-sync` PR carries the
updated state. A saved id is never overridden. Renaming a page's H1 is safe once its id is in
state; renaming a page that is not in state yet creates a new Outline doc and leaves the old one
for a human to delete.

## Script

`scripts/sync_user_guides_outline.py`

```bash
# repo -> Outline (idempotent upsert by stored doc id, then by title)
python scripts/sync_user_guides_outline.py push

# Outline -> repo (used by the scheduled sync)
python scripts/sync_user_guides_outline.py pull

# diff overview, no writes
python scripts/sync_user_guides_outline.py status

# push plan + validation, no network, no token
python3 scripts/sync_user_guides_outline.py dry-run

# validation only (the PR gate), no network, stdlib only
python3 scripts/sync_user_guides_outline.py check
```

State (path → Outline doc id) is stored in `documentation/user-guides/.outline-sync.json`. Commit it. Without state, the script falls back to title matching.

### Env

| Var | Default | Required |
|---|---|---|
| `OUTLINE_API_TOKEN` | - | yes |
| `OUTLINE_BASE_URL` | `https://doc.foundryx.my` | no |
| `OUTLINE_COLLECTION_ID` | `18f78b01-bf5a-4032-934c-d5679609d553` | no |

The script also reads `sorento_crm_backend/.env` automatically (via `python-dotenv`), so locally you only need that file populated.

## Layout

```
documentation/user-guides/
  README.md                        -> Outline root doc "Overview"
  _shared/*.md                     -> parent "Shared" / *
  purchasing/*.md                  -> parent "1-Purchasing" / *
  warehouse/*.md                   -> parent "2-Warehouse" / *
  marketing/*.md                   -> parent "3-Marketing" / *
  project-sales-admin/*.md         -> parent "4-Project Sales Admin" / *
  project-sales-manager/*.md       -> parent "5-Project Sales Manager" / *
  project-sales-rep/*.md           -> parent "6-Project Sales Rep" / *
  technical-team/*.md              -> parent "7-Technical Team" / *
  inventory/*.md                   -> parent "8-Inventory" / *
  delivery-orders/*.md             -> parent "9-Delivery Orders" / *
  product/*.md                     -> parent "10-Product" / *
  sla/*.md                         -> parent "11-SLA" / *
  supply-chain/*.md                -> parent "12-Supply Chain" / *
  procurement/*.md                 -> parent "13-Procurement" / *
  complaints/*.md                  -> parent "14-Complaints" / *
  system-management/*.md           -> parent "15-System Management" / *
  user-management/*.md             -> parent "16-User Management" / *
  commercial/*.md                  -> HELD, never published (HELD_FOLDERS)
```

The folder -> parent map is `PARENT_TITLES` in the script. A new folder must be added there (or
to `HELD_FOLDERS`); `sorento_crm_backend/tests/test_sync_user_guides_guard.py` fails while a guide
folder is in neither, because its pages would silently never reach Outline (and so never reach
the AI assistant, which reads Outline only).

Each markdown file's first H1 (`# Title`) becomes the Outline doc title. The leading H1 is stripped from the body Outline stores (Outline keeps title separately).

## Manual runs

The workflow can still be dispatched by hand (Actions -> Outline user-guides sync -> Run
workflow) with `pull` / `push` / `status` / `dry-run`, plus `force` for a push. Both keep guards
need real commit dates, so the workflow checks out with `fetch-depth: 0`.

### One-time setup

In GitHub repo settings → Secrets and variables → Actions, add:

| Name | Value |
|---|---|
| `OUTLINE_API_TOKEN` | an API token of a dedicated Outline account used only by the sync (see the keep guards above) |
| `OUTLINE_BASE_URL` | `https://doc.foundryx.my` (optional, has default) |
| `OUTLINE_COLLECTION_ID` | `18f78b01-bf5a-4032-934c-d5679609d553` (optional) |

The PR creation step uses `peter-evans/create-pull-request`. The workflow has `contents: write`,
`pull-requests: write` and `issues: write` (for the `docs-sync` label, created on first use)
permissions; no further setup required. Only `OUTLINE_API_TOKEN` is secret; the workflow never
prints it.

## MCP integration

The MCP server (`sorento_crm_mcp`) exposes two tools that read directly from Outline:

- `user_guides_search(query, limit?)` - full-text search over the collection.
- `user_guides_read(identifier)` - fetch the full markdown body by Outline doc id or url-id.

These are registered alongside the catalog-driven CRUD tools. Add `OUTLINE_API_TOKEN` to `sorento_crm_mcp/.env` so the tools work in the MCP container.

## When to push vs pull

- **Edited a guide in the repo?** Merge it to main; the push runs on its own. Watch the run if
  you want to see `[create]` / `[update]` lines.
- **Edited a guide on Outline?** The 6-hourly pull opens a `docs-sync` PR; merge it (or dispatch
  `pull` to get it sooner).
- **In doubt?** Run `status` to see which side has unsynced content.
