# PLAN - Meetings S6: Sorento embed + linkage

**Status:** Planning. UAC: `meetings-sorento-embed-acceptance-criteria.md`. Spine: `foundryx-shared-service/documentation/plans/meetings/PLAN-meetings-program.md`.
**Order:** after shared-service S5. Copies the ideation embed host pattern (`IdeationEmbed`, `useIdeationEmbedSession`, `ideation_embed_service`), generalised only where the second copy proves the need.

## 1. Backend

- Module key `meetings` in `app/modules/meetings/bootstrap.py`; router mounted in `app/api/v1/__init__.py` under `require_module_enabled_with_api_key("meetings")`.
- Permissions `meetings.view`, `meetings.manage` in the permission registry + grant sweep.
- Embed config columns on the existing embed-config row used by ideation (same table, new `meetings_*` columns: connection id, encrypted signing secret, backend base, frontend base). One admin modal, one more section.
- `POST /api/v1/meetings/embed/session` -> mints the assertion and exchanges it at shared-service `POST /meetings/embed/session`; returns `{ token, frontendBase, expiresAt }`.
- `POST /api/v1/external/meetings/ready` (`X-API-Key`, tenant gate): upsert `meeting_links` by attendee email -> `contacts.email`; response `{ linked, unmatched }`.
- `meeting_links(id, meeting_id, entity_type contact|company, entity_id, title, starts_at, status, created_at)`; unique `(meeting_id, entity_type, entity_id)`. Title / date / status are copied so the tab lists without a round trip; they are display copies, not a mirror (minutes never live here).
- `GET /api/v1/meetings/links?entity_type=&entity_id=`, `POST /api/v1/meetings/links`, `DELETE /api/v1/meetings/links/{id}`.
- Migration: one revision, `meeting_links` + embed columns, `down_revision` on the current main head, id under 32 chars.

## 2. Frontend

- `app/(protected)/meetings/my/page.tsx`, `app/(protected)/meetings/all/page.tsx`: `MeetingsEmbed` iframe component with session hook, empty / error state with Retry.
- Contact + company detail: **Meetings** tab = `MeetingLinksPanel` (DataGrid, fixed layout, resizable) + Link meeting (`SearchableSelect`, server search) + Unlink (`ConfirmDeleteDialog`).
- Nav config: Meetings parent, children My meetings (`meetings.view`) and All meetings (`meetings.view`), `moduleKey: 'meetings'`.
- Layering: component -> `useMeetingsEmbedSession` / `useMeetingLinks` hooks -> `services/meetingsService.ts` -> `lib/api-client`. Mock first, swapped last.

## 3. Tests

- pytest: module gate, permission gate, embed session mint against a fake shared-service, ready webhook (match / unmatched / idempotent / wrong tenant 404), link CRUD.
- Vitest: embed panel states, links panel, confirm-on-unlink.
- agent-browser evidence run from the sidebar at 375 px and 1280 px (no new Playwright spec).

## 4. Not in this slice

Minutes content, MCP tools for the AI bubble, action items to tasks, share links.
