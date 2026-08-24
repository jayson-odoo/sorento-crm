# PLAN - CS team market-segment routing (retail / project)

**Status:** Phases 1-3 DONE + self-validated. All UAC passed (BE pytest + FE vitest + browser). No regression (existing suites pass unchanged). Ready for manual eyeball. Uncommitted.
**Slug:** `cs-team-market-segment-routing`
**Owner:** CRM backend + frontend
**Related:** CRM-003 (order tools), `PLAN-procurement-cs-handoff-and-pinpoint-routing.md` (CS PIC pin), `sla_service.py` tier fallback.

---

## Problem

n8n resolves the customer-service assignee for an inbound conversation via:

```
GET /api/v1/external/team-members?agent_code={suggested_agent}&team_code={suggested_team}&tier=1
```

For order enquiries: `suggested_agent=order_enquiries`, `suggested_team=customer_service`, `tier=1`.
Today it returns **every** active member of the resolved team.

Business need: a contact is **retail**, **project**, or **both**. A retail contact must be
routed only to retail CS members; a project contact only to project CS members; a both-contact
to either. The endpoint must return only the members matching the contact's segment(s).

## Locked decisions (user grill #1)

1. **Representation = M2M catalog** (mirrors `ContactAccessType`). New `market_segments` catalog
   (seed `retail`, `project`) + a join on the contact side and a join on the member side.
   "both" = two join rows. Match = **set intersection non-empty**.
2. **Member tag lives on `TeamMember`** (per `(user, team)` membership), not on `User`. A person
   can serve retail in the order_enquiries CS team and project in another team.
3. **Empty match → fall back to ALL members.** A conversation must always resolve to someone; if
   the segment filter yields zero members, return the full active roster (today's behaviour).
4. **Contact segment set manually** in the Contact Details UI (like access types). Untagged
   contacts fall through to "all" (no regression).
5. **Segment routing runs through `team-members` + preferred-assignee.** Only customer-service uses a
   preferred assignee: n8n calls `team-members` (segment-filtered) → picks one → passes
   `preferred_assignee_id` to `next-assignee`, which returns that member directly (RR skipped).
   `next-assignee`'s `contact_id` filter is **strictly opt-in**: when `contact_id` is absent (the
   normal case, incl. all non-CS agents) `next-assignee` behaves **exactly as today** - pure
   round-robin over the full team, **zero regression** (hard requirement + explicit test). It only
   segment-filters the RR pool when a caller explicitly passes `contact_id`.
6. **Untagged member = serves all** (user grill #2, confirms the default below). Migration-safe:
   existing members keep receiving assignments until explicitly tagged.
7. **Segment-scoped RR cursor** (user grill #3): when `contact_id` is passed, RR rotates within the
   contact's segment pool via a segment-keyed cursor; no `contact_id` → the NULL (legacy) cursor,
   unchanged. See Cursor section.
8. **Catalog admin UI in scope** (user grill #3): a Settings screen to manage the `market_segments`
   catalog (add / rename / activate / reorder), plus backend CRUD.
9. **Contact with no segment = ALL segments** (user grill #3): minimum configuration - an untagged
   contact matches every member; nothing needs to be set for today's behaviour to hold.

## Defaulted sub-decisions (documented)

- **Untagged member = serves ALL segments.** (Now locked, decision 6.) A `TeamMember` with zero
  segment rows matches any contact.
- **Contact identifier param = `contact_id`** carrying the `respond_io_id` value, matching the
  existing `GET /external/contact-access-types/active` convention (`contact_id` = respond_io_id).
  Optional `space_id` accepted for multi-workspace disambiguation; when omitted, resolve the first
  contact by `respond_io_id`. Param omitted entirely → no filter (backward compat).
- **Both-segment contact** (`[retail, project]`) → union of retail and project members (intersection
  with each tagged member is non-empty for whichever they serve).
- **Filter is response-only.** No change to round-robin cursors or `next-assignee` in phase 1
  (see Open item O1).

## Match algorithm (the one source of truth)

`list_active_team_members_detail(team_id, contact_segments: set[str] | None)`:

```
active = active members of team_id
if not contact_segments:                      # no contact / untagged contact / param omitted
    return active                             # unfiltered - today's behaviour
filtered = [m for m in active
            if not m.segments                 # untagged member serves all
            or (m.segments & contact_segments)]  # intersection non-empty
return filtered if filtered else active       # fall back to all when empty (decision 3)
```

## Round-robin cursor: segment-scoped (locked)

The RR cursor is per `(agent_id, team_id)` (`agent_team_round_robin_cursors`). Decision: **scope the
cursor by the contact's segment** so each segment rotates independently and fairly over its own pool.

- Add a nullable `segment_key VARCHAR(120)` column to `agent_team_round_robin_cursors`; extend the
  unique key to `(agent_id, team_id, segment_key)`.
- **`segment_key = NULL`** is the legacy cursor - used whenever `next-assignee` gets **no `contact_id`**
  (the normal RR path). This row is byte-identical to today → **zero regression**.
- When `contact_id` IS passed and the contact has segment(s), `segment_key` = the sorted, `|`-joined
  contact-matched segment codes (e.g. `"retail"`, `"project"`, or `"project|retail"` for a both-contact).
  RR advances within the segment-filtered pool using that keyed cursor.
- **Contact has NO segment** (untagged) → treated as **all segments** → no filter, and the cursor used
  is the `NULL` (legacy) cursor - so a fully-unconfigured setup behaves exactly as today. This is the
  "minimum configuration" guarantee: leave contacts untagged and nothing changes.
- Empty filtered pool → fall back to the full team (and the `NULL` cursor).

Migration `263` (or a paired `264`) adds the column + widens the unique index; existing cursor rows
get `segment_key = NULL`, preserving their current position.

## Data model

New catalog + two join tables (all additive; no column added to hot tables beyond joins).

```
market_segments                       -- catalog (admin-manageable, seeded)
  code         VARCHAR(50) PK         -- 'retail', 'project'
  name         VARCHAR(255) NOT NULL  -- 'Retail', 'Project'
  is_active    BOOLEAN default true
  sort_order   INTEGER null
  created_at   timestamptz

respond_contact_market_segments       -- contact ↔ segment (M2M)
  contact_id      TEXT   FK respond_contacts.id      ON DELETE CASCADE
  segment_code    VARCHAR(50) FK market_segments.code ON DELETE CASCADE
  PK (contact_id, segment_code)
  index (contact_id), index (segment_code)

team_member_market_segments           -- team membership ↔ segment (M2M)
  team_member_id  UUID   FK team_members.id          ON DELETE CASCADE
  segment_code    VARCHAR(50) FK market_segments.code ON DELETE CASCADE
  PK (team_member_id, segment_code)
  index (team_member_id), index (segment_code)
```

Migration: create the three tables + seed `market_segments` with `retail`, `project`. Idempotent
(`IF NOT EXISTS`, `ON CONFLICT DO NOTHING` on seed). Alembic head is `262_chat_history_reply_to`;
new revision `263_market_segments`.

Models (`app/models/access.py`): `MarketSegment`, two `Table()` joins, and relationships
`RespondContact.market_segments` (secondary) + `TeamMember.market_segments` (secondary). Mirror the
exact pattern of `ContactAccessType` / `respond_contact_access_types` already in the file.

## Backend changes

| File | Change |
|------|--------|
| `alembic/versions/263_market_segments.py` | Create catalog + 2 join tables, seed retail/project. Idempotent. |
| `app/models/access.py` | `MarketSegment` model, 2 join `Table`s, secondary relationships on `RespondContact` + `TeamMember`. |
| `app/services/user_service.py` `list_active_team_members_detail` | Add `contact_segments: set[str] \| None = None`; apply the match algorithm above (eager-load member segments to avoid N+1). |
| `app/services/user_service.py` `get_next_assignee` | Add optional `contact_segments=None`. **When None → current behaviour, untouched** (pure RR over full team). When a set is passed → restrict the RR pool to segment-matched members (untagged member always in pool) before advancing the cursor; empty pool → fall back to full team. See Cursor note. |
| `app/api/v1/external/next_assignee.py` | Read **optional** `contact_id` (respond_io_id) from the POST body. **Absent → do not resolve/pass segments at all → identical to today (no regression).** Present → resolve segments → pass to `get_next_assignee`. `preferred_assignee_id` path unchanged. |
| `app/api/v1/external/team_members.py` | Add `contact_id` (respond_io_id) + optional `space_id` query params. Resolve contact → its active segment codes → pass to service. Missing/unknown contact → no filter (log + unfiltered), never 404 (assignment must not break). |
| `app/services/user_service.py` `get_next_assignee` cursor read/advance | Use `segment_key` (NULL when no `contact_id`) to select/advance the correct cursor row within the filtered pool. |
| `app/models/access.py` `AgentTeamRoundRobinCursor` | Add `segment_key VARCHAR(120)` nullable; widen unique key to `(agent_id, team_id, segment_key)`. |
| `app/services/market_segment_service.py` (new) | `resolve_contact_segments(respond_io_id, space_id=None) -> set[str]`; `segment_key_for(segments) -> str\|None`; catalog CRUD; contact + member segment assignment used by the internal FE endpoints. |
| `app/api/v1/system/market_segments.py` (new, internal JWT) | Catalog CRUD: `GET/POST/PUT/DELETE` market segments (add / rename / activate / reorder) for the Settings admin screen. Hard-delete guarded when in use (block or cascade-warn per delete standard). |
| `app/api/v1/user_management/*` (contact + member segment endpoints) | Internal (JWT) endpoints to GET/PUT a contact's segments and a team-member's segments, for the FE editors. |
| `app/schemas/...` | Response/request schemas for the catalog CRUD + segment assignment editors. |

Endpoint contract (external, unchanged shape, new optional inputs):

```
GET /api/v1/external/team-members
    ?agent_code=order_enquiries&team_code=customer_service&tier=1
    &contact_id={respond_io_id}          # NEW, optional
    [&space_id={space_id}]               # NEW, optional
->
[ {user_id, name, respond_user_id, email, sort_order}, ... ]   # same shape, filtered
```

n8n adds `&contact_id={{ ...respond_io_id }}` to its existing call. Omitting it = today's behaviour.

## Frontend changes (three-phase: prototype first)

- **Contact Details** (`app/(protected)/user-management/contacts/[id]/page.tsx`): new **Market
  Segment** section in the Contact Information card (sits beside Access types). Badges + an editor
  (multi-select retail/project) → PUT contact segments. Always render the section with an empty
  state per ADR-PRODUCT-STANDARDS.
- **Access Agent Detail** (`app/(protected)/user-management/access-agents/components/AccessAgentDetail.tsx`)
  → team assignment → member roster: per-member **Segment** multi-select (retail/project/both = both
  selected). Writes team-member segments. This is the "agent teams configuration" the user referred to.
- **Settings → Market Segments** (catalog admin): a DataGrid listing catalog rows (code, name,
  active, sort_order) with Add / Edit (modal) / Activate-toggle / reorder, and hard-delete +
  confirmation dialog (blocked or cascade-warned when the segment is assigned to any contact/member).
  Follows CRUD UX standard (DataGrid + Add toolbar, modal create/edit, `AlertDialog` delete). Route
  under the existing system/settings area (mirror another catalog screen, e.g. contact access types).
- Reuse existing badge/multiselect components; no UUIDs in UI (segment codes are human labels).

## Tests (Phase 2, not deferred)

- **pytest** `tests/test_team_member_segment_routing.py` (live PG, seeded prefix):
  - retail contact → only retail + untagged members; project contact → only project + untagged.
  - both-contact → union.
  - contact untagged → all members (no filter).
  - `contact_id` omitted → all members (byte-identical to today).
  - unknown/other-workspace `contact_id` → all members (no 404, logged).
  - **empty match → fall back to all** (retail contact, only project members tagged).
  - segment filter ANDs correctly with tier resolution (`tier=1` team only).
- **pytest** `next-assignee` **regression guard (primary):** with NO `contact_id` in the body, the
  full existing round-robin sequence is byte-identical to today (cursor advances over the full team,
  same order) - for a CS team AND a non-CS team. This is the hard no-regression requirement.
- **pytest** `next-assignee` opt-in segment path: WITH `contact_id`, RR pool is segment-filtered
  (untagged member included); `preferred_assignee_id` still returns directly; empty pool → falls
  back to full team; cursor advances within the pool.
- **pytest** catalog CRUD (`app/api/v1/system/market_segments.py`): create/rename/activate/reorder;
  hard-delete blocked/cascade-warned when assigned; auth denial + validation.
- **vitest**: Contact Market Segment editor (loading/empty/error/data) + member segment multiselect +
  Settings Market Segments DataGrid (list/add/edit/delete-confirm states).
- **playwright**: tag a contact retail in Contact Details → assert persisted; MCP-verify the external
  call returns the filtered roster.

## Resolved & remaining

- **O1 - `next-assignee` alignment.** RESOLVED (decision 5): CS routing runs through `team-members` +
  `preferred_assignee_id`. `next-assignee` segment filtering is opt-in via `contact_id`; absent (the
  normal RR path, all non-CS agents) → **no behaviour change, no regression**. Cursor approach = note
  above, only reached when `contact_id` is explicitly passed.
- **O2 - Untagged-member semantics.** RESOLVED (decision 6): untagged member = serves all.
- **O3 - Catalog manageability.** RESOLVED (decision 8): full Settings admin screen + backend CRUD
  in scope (seed retail/project, admin can add/rename/activate/reorder).
- **O4 - Who owns the contact tag long-term.** Manual now (decision 4). Future: sync from a
  Respond.io field or derive from the customer record - out of scope, noted for later.

## Phasing

1. **Phase 1 - FE prototype** (mocks): Contact Market Segment section + member segment multiselect,
   all states, screenshots. No backend.
2. **Phase 2 - BE + wire + tests:** migration/models/service/endpoint + internal CRUD endpoints,
   FE off mocks, all three test suites green. n8n adds `&contact_id=`.
3. **Phase 3 - review:** `/code-review`, PR-CHECKLIST, then PR.
