# User-guides ↔ Outline two-way sync

The user guides under `documentation/user-guides/` are mirrored to the **Sorento CRM** collection on Outline (`https://doc.foundryx.my/collection/sorento-crm-BOoUtlxxTH`). MCP tools, the in-app footer "Docs" link, and the n8n / WhatsApp agent all read from Outline at runtime, so Outline is the user-facing source of truth.

The repo copy is kept in sync so that:

- Engineering can review documentation changes in PRs.
- Outline outages don't break local AI tooling (the markdown is still on disk).
- Edits made by non-engineers in Outline land back in git automatically.

## Script

`scripts/sync_user_guides_outline.py`

```bash
# repo -> Outline (idempotent upsert by stored doc id, then by title)
python scripts/sync_user_guides_outline.py push

# Outline -> repo (used by the scheduled sync)
python scripts/sync_user_guides_outline.py pull

# diff overview, no writes
python scripts/sync_user_guides_outline.py status
```

State (path → Outline doc id) is stored in `documentation/user-guides/.outline-sync.json`. Commit it. Without state, the script falls back to title matching.

### Env

| Var | Default | Required |
|---|---|---|
| `OUTLINE_API_TOKEN` | — | yes |
| `OUTLINE_BASE_URL` | `https://doc.foundryx.my` | no |
| `OUTLINE_COLLECTION_ID` | `18f78b01-bf5a-4032-934c-d5679609d553` | no |

The script also reads `sorento_crm_backend/.env` automatically (via `python-dotenv`), so locally you only need that file populated.

## Layout

```
documentation/user-guides/
  README.md                        -> Outline root doc "Overview"
  _shared/
    upload-flow.md                 -> parent "Shared" / Upload flow
  purchasing/*.md                  -> parent "Purchasing" / *
  warehouse/*.md                   -> parent "Warehouse" / *
  marketing/*.md                   -> parent "Marketing" / *
  project-sales-admin/*.md         -> parent "Project Sales Admin" / *
  project-sales-manager/*.md       -> parent "Project Sales Manager" / *
  project-sales-rep/*.md           -> parent "Project Sales Rep" / *
```

Each markdown file's first H1 (`# Title`) becomes the Outline doc title. The leading H1 is stripped from the body Outline stores (Outline keeps title separately).

## Scheduled sync (Outline → repo)

`.github/workflows/outline-user-guides-sync.yml` runs every 6 hours, pulls the current Outline state, and opens a PR (`bot/outline-user-guides-sync`) if anything changed. Workflow can also be triggered manually with the `pull` / `push` / `status` choice.

### One-time setup

In GitHub repo settings → Secrets and variables → Actions, add:

| Name | Value |
|---|---|
| `OUTLINE_API_TOKEN` | your Outline API token (workspace-scoped) |
| `OUTLINE_BASE_URL` | `https://doc.foundryx.my` (optional, has default) |
| `OUTLINE_COLLECTION_ID` | `18f78b01-bf5a-4032-934c-d5679609d553` (optional) |

The PR creation step uses `peter-evans/create-pull-request`. The workflow has `contents: write` and `pull-requests: write` permissions; no further setup required.

## MCP integration

The MCP server (`sorento_crm_mcp`) exposes two tools that read directly from Outline:

- `user_guides_search(query, limit?)` — full-text search over the collection.
- `user_guides_read(identifier)` — fetch the full markdown body by Outline doc id or url-id.

These are registered alongside the catalog-driven CRUD tools. Add `OUTLINE_API_TOKEN` to `sorento_crm_mcp/.env` so the tools work in the MCP container.

## When to push vs pull

- **Edited a guide locally?** → run `push` (or merge to main, then run push from your machine).
- **Edited a guide on Outline?** → wait for the scheduled job (or trigger the workflow manually with `pull`).
- **In doubt?** → run `status` to see which side has unsynced content.
