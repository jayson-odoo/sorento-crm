# Ticketing System Module - Plan

> **Status**: Plan approved, implementation in progress on `claude/ticketing-system-gJGvI`.
> Backend module skeletons (`app/modules/{activities,tickets}/`), models, and schemas are
> already committed; everything else listed below is still pending.

## Context

The frontend footer's "Support" button currently points to `https://devs.keenthemes.com` (`app/components/layouts/demo10/components/footer.tsx:50`) and goes nowhere useful. Internal users need a Jira-style ticketing system to raise issues, attach screenshots, get assigned to a teammate, track resolution progress, and converse with the submitter through Respond.io.

The work has two parts:

### A. Build a new shared base module: `ActivitiesNotesPanel`

The user already has this pattern shipping in their sister product (the **`ijm-icp-crm`** repo, deployed at `*-demo.foundryx.my`) and shared reference screenshots. It does NOT exist in sorento-crm yet, but it's a generic primitive that the ticketing module - and future modules like leads/complaints/orders - will all consume. We build it once as a base shared component and a base backend service.

> **Implementation prerequisite**: Before coding, port the existing implementation from `ijm-icp-crm` 1:1 (component file, hooks, backend models, endpoints) and only adapt the registry adapter to fit sorento-crm's modules. GitHub MCP access is currently restricted to `jayson-odoo/sorento-crm` only, so this requires either (a) cloning `ijm-icp-crm` into `/home/user/` so the agent can read it directly, or (b) granting MCP access to that repo. If neither is available at implementation time, build to the screenshot spec below as a faithful approximation.

Behaviour (from screenshots):
- A floating red pulse-icon launcher pinned to the right edge of any detail page that mounts the panel.
- Click → the panel opens on the right side. **Pushes** main content (does not overlay): on `lg+` it occupies a fixed `420px` column and the main content shrinks; on small screens it goes full-width (the main content is effectively pushed off-screen - same code path, same animation).
- Header: "Activities & notes" + "Activities are visible to everyone with access. Internal notes are private to you." + close ×.
- Three icon-tabs: **Activities** (pulse), **Internal Notes** (document), **Messages** (chat-bubble linked to Respond.io contact).
- **Activities** = chronological feed mixing system events ("LD-2026-0008 is created.", "LD-2026-0008 moved to Qualified.") with user updates posted from the rich-text composer. Composer supports @-mentions, paragraph/heading style switcher, B/I/U/S, ordered/unordered lists, link, clear-formatting, attachment paperclip, emoji picker, "Post" button.
- **Internal Notes** = private to the current user, identical composer with placeholder "Private notes (only you can see these)…".
- **Messages** = Respond.io conversation. Top: "Choose a contact" select that lists the entity's linked Respond contacts (a ticket has one - the submitter). Body: incoming/outgoing bubble thread for that contact. Composer footer reads "Choose a contact to reply." until a contact is selected.

The panel is **entity-generic**: it accepts `entityType` (string) and `entityId` (uuid) and contacts a single set of endpoints. The ticketing module is the first consumer; other modules can mount it later by passing their own type/id and registering their entity in the backend.

### B. Build the Ticketing System module on top of it

Requirements baked in from the conversation:
- Status workflow: `draft → submitted → assigned → responded → resolved`. Both DataGrid list view and Kanban board view (drag a card to change status).
- Visibility: hard server-side enforcement - non-admins see only tickets where they are `raised_by`, `assigned_to`, or a watcher. `tickets.tickets.view_all` unlocks everything.
- Status-change permission: only the assignee or admin/superadmin can move a card.
- Comments: live entirely in the shared `ActivitiesNotesPanel` Activities tab. Posting an update as the assignee while ticket is `assigned` auto-flips the status to `responded` (recorded as a system Activities event).
- Extra fields: priority (low/medium/high/urgent), category (bug/feature/question/other), due date, watchers (CC list).
- Ticket carries dedicated **Response** and **Resolution** rich-text fields (separate from activity feed) and tracks **response time** + **resolution time** the same way `ConversationSLATracking` does for conversations (see SLA section below).
- Attachments inline in description and on the ticket itself, uploaded to R2 via existing storage router.

---

## Backend (`sorento_crm_backend/`)

### 1. Activities & Notes - base shared infrastructure

#### Module skeleton - DONE
- `app/modules/activities/__init__.py`, `bootstrap.py` (`MODULE_KEY = "activities"`), `manifest.py` (`DISPLAY_NAME="Activities & Notes"`, `DEPENDENCIES=("base","resources")`).

#### Models (`app/models/activities.py`) - DONE
Generic `(entity_type, entity_id)` indirection so any module can plug in.

- **`ActivityEvent`** - the Activities feed.
  - `id` uuid, `entity_type` string, `entity_id` string, `kind` string (`system` | `user_update`), `body_html` text (nullable for system), `body_text` text, `system_template` string nullable (e.g. `"entity.created"`, `"status.changed"`), `system_payload` JSONB nullable (e.g. `{"from":"submitted","to":"assigned"}`), `actor_id` uuid (nullable for system), `created_at`. Index `(entity_type, entity_id, created_at)`.
  - Linked attachments via the existing `EntityAttachmentLink` table with `entity_type='activity_event'`.
- **`InternalNote`** - private notes.
  - `id`, `entity_type`, `entity_id`, `author_id`, `body_html`, `body_text`, `created_at`, `updated_at`. Index `(entity_type, entity_id, author_id, created_at)`.
- **`ActivityMention`** - for @-mentions, drives notifications.
  - `id`, `activity_event_id` (FK cascade), `mentioned_user_id`, `seen_at` nullable.

Per-module config registered in code: each consuming module declares `entity_type` + a function that returns the linked Respond contact id(s) for a given `entity_id` (used by the Messages tab). Stored in `app/services/activities_registry.py`:

```python
ACTIVITIES_REGISTRY[entity_type] = ActivitiesAdapter(
    entity_type="ticket",
    permission_view="tickets.tickets.view",
    permission_post="tickets.tickets.view",     # post = anyone who can see
    get_respond_contacts=lambda db, ticket_id: tickets_service.respond_contacts_for(db, ticket_id),
    on_post=lambda db, ticket_id, actor_id, body_html: tickets_service.handle_activity_posted(db, ticket_id, actor_id),
    visibility_filter=lambda db, current_user: tickets_service.activity_visibility_filter(current_user),
)
```

The `on_post` callback is what drives the auto-flip `assigned → responded` for tickets - generic infra, ticket-specific behaviour.

#### Schemas (`app/schemas/activities.py`) - DONE
- `ActivityEventResponse`, `ActivityEventCreate`, `InternalNoteResponse`, `InternalNoteCreate`, `InternalNoteUpdate`, `EntityRespondContact`, `EntityMessageSendRequest`, `ActivityActor`.

#### Service (`app/services/activities_service.py`) - TODO
- `list_activities(entity_type, entity_id, current_user, limit, before_cursor)` - runs through registry adapter for visibility + access check; returns a merged feed of `ActivityEvent` rows + a flat representation of `audit_logs` system events (for cheap entry-creation/status events emitted by `__audit_track__` listeners we don't double-write).
- `post_activity(entity_type, entity_id, body_html, attachment_ids, mentioned_user_ids, current_user)` - write ActivityEvent (`kind=user_update`), link attachments, write mentions, fire `on_post` adapter callback, fire notification job for mentions.
- `record_system_event(db, entity_type, entity_id, template, payload, actor_id)` - call this from any service when something noteworthy happens (e.g. `tickets_service.change_status` calls it with `template="status.changed"`).
- `list_internal_notes(...)`, `post_internal_note(...)`, `update_internal_note(...)`, `delete_internal_note(...)` - strictly scoped to `author_id == current_user.id`.
- `list_messages(entity_type, entity_id, contact_id, cursor)` - proxies to Respond.io via the existing `respond` integration code path; uses the registry's `get_respond_contacts` to validate the contact actually belongs to the entity.
- `send_message(entity_type, entity_id, contact_id, body, attachment_ids)` - proxies outbound to Respond.io and writes a system `ActivityEvent` "Message sent to {contact}" so the Activities feed reflects it.

#### Routes (`app/api/v1/activities/activities.py`) - TODO
Mount in `app/api/v1/__init__.py` with prefix `/activities`, tag `activities`, `dependencies=[Depends(require_module_enabled_with_api_key("activities"))]`:

- `GET  /activities/{entity_type}/{entity_id}/activities`
- `POST /activities/{entity_type}/{entity_id}/activities`
- `GET  /activities/{entity_type}/{entity_id}/notes`
- `POST /activities/{entity_type}/{entity_id}/notes`
- `PATCH /activities/notes/{note_id}`
- `DELETE /activities/notes/{note_id}`
- `GET  /activities/{entity_type}/{entity_id}/contacts` - lists Respond contacts for the entity (driven by registry adapter).
- `GET  /activities/{entity_type}/{entity_id}/messages?contact_id=...`
- `POST /activities/{entity_type}/{entity_id}/messages` - body `{contact_id, body, attachment_ids}`.
- `POST /activities/{entity_type}/{entity_id}/mentions/{event_id}/seen` - mark a mention as seen.

### 2. Tickets module

#### Module skeleton - DONE
`app/modules/tickets/{__init__.py,bootstrap.py,manifest.py}` - `MODULE_KEY="tickets"`, `DEPENDENCIES=("base","resources","activities")`, `GUARD_KEY="tickets"`, `USE_API_KEY_GUARD=True`.

#### Models (`app/models/tickets.py`) - DONE
`__audit_track__=True`, `__audit_entity_type__="ticket"`. SQLAlchemy listeners that translate `__audit_track__` change rows into `ActivityEvent(kind="system", template="...")` are still **TODO**.

- **`Ticket`**:
  - Identity: `id` uuid, `ticket_number` text monotonic (`TCK-2026-000123`).
  - Core: `title`, `description_html`, `description_text`.
  - Workflow: `status` default `draft`, `priority` default `medium`, `category` default `question`, `due_date` nullable.
  - People: `raised_by` uuid → users.id, `assigned_to` uuid → users.id nullable.
  - **Response & Resolution payloads** (rich text on the ticket itself): `response_html`, `response_text`, `responded_by`; `resolution_html`, `resolution_text`, `resolved_by`.
  - **SLA timestamps & durations** (mirror `ConversationSLATracking`): `submitted_at`, `assigned_at`, `first_response_at`, `responded_at`, `resolved_at`, `response_time_hours` numeric(10,2), `resolution_time_hours` numeric(10,2), `sla_response_due_at`, `sla_resolution_due_at`.
  - Bookkeeping: `created_at`, `updated_at`. Indexes on `status`, `assigned_to`, `raised_by`, `priority`, `due_date`, `sla_response_due_at`.
- **`TicketWatcher`**: `id`, `ticket_id` (FK cascade), `user_id`, `added_at`, `added_by`. Unique `(ticket_id, user_id)`.
- **`TicketRespondContactLink`**: `id`, `ticket_id` (FK cascade), `respond_contact_id`, `is_primary` bool, `created_at`. The submitter's Respond contact (resolved by phone match) is auto-linked on create.

No standalone `TicketComment` table - comments live in `ActivityEvent`. No standalone `TicketStatusHistory` table - status transitions are recorded as system `ActivityEvent` rows (`template="status.changed"`, `payload={"from":"submitted","to":"assigned"}`) plus the `audit_logs` row written by `__audit_track__`.

#### Schemas (`app/schemas/tickets.py`) - DONE
- `TicketCreate` (`save_as_draft: bool=False`), `TicketUpdate` (all optional), `TicketResponse` (full, with nested `raised_by_user`, `assigned_to_user`, `responded_by_user`, `resolved_by_user`, `attachments`, `watchers`, `respond_contacts`, plus computed `is_overdue_response`, `is_overdue_resolution`).
- `TicketStatusChangeRequest`, `TicketAssignRequest`, `TicketResponseUpdate`, `TicketResolutionUpdate`, `TicketWatchersUpdate`, `TicketKanbanResponse`, `BulkDeleteTicketsRequest`.

#### Service (`app/services/tickets_service.py`) - TODO
- `list(filters, limit, offset, current_user)` - without `tickets.tickets.view_all`, force `(raised_by=me OR assigned_to=me OR EXISTS watcher)`. Filters: `status`, `assigned_to`, `raised_by`, `priority`, `category`, `due_before`, `q` (title + description_text + ticket_number).
- `kanban(filters, current_user)` - same filters, returns `{ status_key: TicketResponse[] }` capped at e.g. 100 / column.
- `get(id, current_user)` - same visibility, 404 (not 403) when invisible.
- `create(data, current_user)` - sets `raised_by=current_user.id`, generates `ticket_number`, status `draft` if `save_as_draft` else `submitted` (sets `submitted_at`, sets `sla_response_due_at = submitted_at + policy.response_window`). Auto-links submitter's Respond contact via phone match. Records system activity.
- `update(id, data, current_user)`, `delete(id, current_user)`.
- `change_status(id, new_status, current_user, note)` - validates the transition (any→any except `resolved→draft`); only assignee or admin can call. Updates the matching timestamp:
  - `submitted` → sets `submitted_at`, computes `sla_response_due_at`.
  - `assigned` → sets `assigned_at`.
  - `responded` → sets `responded_at`, sets `first_response_at` if null, sets `response_time_hours = (first_response_at - submitted_at) / 3600`.
  - `resolved` → sets `resolved_at`, `resolved_by`, `resolution_time_hours = (resolved_at - submitted_at) / 3600`.

  Records system `ActivityEvent` with `template="status.changed"`, `payload={"from":..., "to":..., "note":...}`.
- `assign(id, assignee_id, current_user)` - admin-only, sets `assigned_to`, `assigned_at`, auto-bumps `submitted → assigned`. Records system activity `template="assignee.changed"`.
- `update_response(id, response_html, current_user)` / `update_resolution(id, resolution_html, current_user)` - assignee/admin only. First call to update_response sets `first_response_at` + `response_time_hours` and auto-flips status `assigned → responded`. Resolution update auto-flips status `responded → resolved` and sets `resolution_time_hours`.
- `add_watchers / remove_watcher` - assignee/admin only.
- `handle_activity_posted(db, ticket_id, actor_id)` - Activities-registry callback. If actor == `assigned_to` and status == `assigned`, call `change_status(ticket_id, "responded", actor, note=None)`.
- `respond_contacts_for(db, ticket_id)` / `activity_visibility_filter(current_user)` - Activities-registry callbacks.

#### Routes (`app/api/v1/tickets/tickets.py`) - TODO
Mount with prefix `/tickets-management`, tag `tickets`, `dependencies=[Depends(require_module_enabled_with_api_key("tickets"))]`:
- `GET|POST /tickets-management/tickets`
- `GET|PATCH|DELETE /tickets-management/tickets/{id}`
- `GET /tickets-management/tickets/kanban`
- `POST /tickets-management/tickets/{id}/status`
- `POST /tickets-management/tickets/{id}/assign`
- `PUT  /tickets-management/tickets/{id}/response`
- `PUT  /tickets-management/tickets/{id}/resolution`
- `POST|DELETE /tickets-management/tickets/{id}/watchers[/{user_id}]`
- `POST /tickets-management/tickets/{id}/attachments`, `DELETE /tickets-management/tickets/attachments/{link_id}` (uses `EntityAttachmentService`).

Activities/notes/messages for a ticket are reached at the generic `/activities/ticket/{id}/...` endpoints - no per-module duplication.

### 3. List query registry (`app/services/list_query_registry.py`) - TODO
Register `tickets` with `view_slug="tickets.tickets.view"`, `export_slug="tickets.tickets.export"`.

### 4. RBAC (`app/rbac/permission_registry.py`) - TODO
```python
PERMISSION_REGISTRY.extend(_crud("tickets", "tickets", "Tickets"))
PERMISSION_REGISTRY.append({"slug": "tickets.tickets.view_all", "name": "View all tickets (admin)", "description": "..."})
PERMISSION_REGISTRY.append({"slug": "tickets.tickets.assign", "name": "Assign tickets", "description": "..."})
PERMISSION_REGISTRY.append({"slug": "tickets.tickets.export", "name": "Export tickets", "description": "..."})
```
Auto-assign `view_all`, `assign`, `delete` to `admin`/`superadmin`. Activities permissions reuse `tickets.tickets.view` for visibility (anyone who can see the ticket can read/post activities).

### 5. Alembic - TODO
- `166_create_activities_module.py` - `activity_events`, `internal_notes`, `activity_mentions`.
- `167_create_tickets_module.py` - `tickets`, `ticket_watchers`, `ticket_respond_contact_links`.
- `168_seed_tickets_rbac.py` - `sync_permissions(session)`.
- `168` also calls the activities-registry adapter registration for tickets at startup (in `app/main.py` startup).

---

## Frontend (`sorento_crm_frontend/`)

### 1. Footer wiring - TODO
`app/components/layouts/demo10/components/footer.tsx:50` - replace the `https://devs.keenthemes.com` href with `/ticket-management/tickets` and drop `target="_blank"`.

### 2. Sidebar menu - TODO
`config/menu.config.tsx` - add a "Ticket Management" group (icon `LifeBuoy`), `moduleKey: 'tickets'`, child `{ title: 'Tickets', path: '/ticket-management/tickets' }`.

### 3. Shared `ActivitiesNotesPanel` (NEW base component) - TODO

#### Files
```
components/common/ActivitiesNotesPanel/
  index.tsx                         # public export
  ActivitiesNotesPanel.tsx          # the panel shell + tab logic
  ActivitiesNotesLauncher.tsx       # the floating right-edge pulse-icon button
  EntityActivitiesLayout.tsx        # the push-not-overlay layout primitive
  ActivitiesTab.tsx                 # Activities feed
  InternalNotesTab.tsx              # private notes
  MessagesTab.tsx                   # Respond.io contact messages
  ActivityComposer.tsx              # rich-text + paperclip + emoji + post
  ActivityFeedItem.tsx              # one row in the feed (system or user)
  hooks/
    useActivitiesPanel.ts           # open/close state + persistence (per-entity)
    useActivities.ts                # query + post mutations
    useInternalNotes.ts             # query + post/edit/delete
    useEntityRespondContacts.ts     # GET contacts list
    useEntityMessages.ts            # GET messages, POST send
  services/
    activitiesPanelService.ts       # all API calls (entityType-generic)
  types/
    activities-panel.types.ts
```

Public API:
```tsx
<ActivitiesNotesPanel entityType="ticket" entityId={ticket.id} />
```
The component renders **both** the floating launcher and the slide-in panel. It is responsible for its own open/close state but persists last-opened-tab in `localStorage` keyed on `entityType` so users land back on the same tab.

#### Layout - push, not overlay

The panel cannot use `Sheet` (which overlays). Instead, the host page wraps its content in a layout primitive that allocates space to the panel when open. Implementation:

```tsx
// In a host page (e.g. ticket detail):
<EntityActivitiesLayout entityType="ticket" entityId={id}>
  <TicketDetailBody ticket={ticket} />
</EntityActivitiesLayout>
```

`EntityActivitiesLayout` (`components/common/ActivitiesNotesPanel/EntityActivitiesLayout.tsx`):
```tsx
const { isOpen } = useActivitiesPanel(entityType, entityId);
return (
  <div className="relative flex min-h-[calc(100vh-var(--header-h))] w-full">
    <main className={cn(
      "flex-1 transition-[margin] duration-200 ease-out",
      isOpen ? "lg:mr-[420px]" : "mr-0"   // PC: push by panel width
    )}>
      {children}
    </main>
    <ActivitiesNotesLauncher /> {/* floating button, hidden when open */}
    <aside className={cn(
      "fixed top-0 right-0 z-30 h-full bg-background border-l shadow-xl",
      "w-full lg:w-[420px]",
      "transition-transform duration-200 ease-out",
      isOpen ? "translate-x-0" : "translate-x-full"
    )}>
      <ActivitiesNotesPanel entityType={entityType} entityId={entityId} />
    </aside>
  </div>
);
```

So on `lg+` the panel is a 420px column that pushes the main content (mr increases when open); on small screens the main content keeps `mr-0` but the panel covers it full-width - same animation, same code.

#### Visual spec (matches screenshots exactly)

- Header `p-5 border-b`: title `text-lg font-semibold` "Activities & notes", `text-sm text-muted-foreground` description, top-right `<Button variant="ghost" size="icon">` with `<X>` to close.
- Tab strip: a `ToggleGroup` (3 items, icon-only). Selected item gets `bg-background` with red icon (`text-red-600`); unselected has muted icon. Wrapper has `bg-muted/30 rounded-lg p-0.5` like `ListBoardViewToggle`.
  - Activity icon = `Activity` (or `HeartPulse`) from lucide.
  - Internal Notes icon = `FileText`.
  - Messages icon = `MessageSquare`.
- Body: `flex-1 overflow-y-auto p-4 space-y-3`. Each feed item is a soft card: `bg-muted/30 border rounded-md p-3` with header row `[<Badge variant="secondary">System</Badge>] [text-xs text-muted-foreground]{timestamp}` and body in `text-sm`. User updates use the same card with author Avatar + name instead of "System" badge, and the body is rendered HTML in a `prose prose-sm` wrapper.
- Footer composer: sticky `border-t p-3` containing:
  - Toolbar row: heading-style switcher ("Normal" `<Select>`), B / I / U / S, ordered/unordered list, link, clear-formatting (`Tx`). Icons via lucide.
  - `<RichTextEditor>` (Tiptap) with placeholder "Share an update… Use @ to mention someone." (or "Private notes (only you can see these)…" or "Choose a contact to reply." depending on tab + state).
  - Action row: `<Paperclip>` (attach), `<Smile>` (emoji picker via `components/ui/popover.tsx` + a small grid; can use `cmdk` we already ship), spacer, `<Button>Post</Button>` (red primary, disabled when empty / no contact selected).
- Mentions: typing `@` in the editor opens a Tiptap mention extension popup populated by `getUsersSelect()`; selected mentions become inline `<span class="text-primary">@Name</span>` chips and are sent as `mentioned_user_ids` on submit.

#### Tabs

- **Activities**: `useActivities(entityType, entityId)` → infinite query reverse-paged. System events render with the `System` badge and a fixed phrasing computed from `system_template + payload` (e.g. `"{ticket_number} moved to {to_status}"`). User updates render with author. Composer posts via `useActivities().postActivity(body_html, attachment_ids, mentioned_user_ids)`.
- **Internal Notes**: `useInternalNotes(entityType, entityId)` - reverse-paged list filtered to current user. Composer placeholder swaps to private-notes copy. Each note has an inline edit + delete (uses `ConfirmDeleteDialog`).
- **Messages**: `useEntityRespondContacts` → contact `<Select>` at the top. When picked, `useEntityMessages(entityType, entityId, contactId)` loads the inbox-style thread (incoming/outgoing bubbles, identical to existing `ComplaintConversationPanel` rendering - which we *factor out* into a small shared `RespondMessageBubble` component while we're here). Composer footer reads "Choose a contact to reply." until a contact is picked.

### 4. Ticket routes (`app/(protected)/ticket-management/tickets/`) - TODO

```
page.tsx                      # List + Kanban (?view=list|board)
[id]/page.tsx                 # Detail page (wraps body in EntityActivitiesLayout)
components/
  TicketsList.tsx
  TicketsKanban.tsx
  TicketFormDialog.tsx        # Create/edit modal
  TicketDetail.tsx            # Header + body
  TicketDetailSidebar.tsx     # right-side details (status, assignee, priority, due, watchers)
  TicketResponseCard.tsx      # the Response rich-text card (inline-edit)
  TicketResolutionCard.tsx    # the Resolution rich-text card (inline-edit)
  TicketSlaStrip.tsx          # response/resolution time + SLA due chips
  TicketStatusBadge.tsx
  TicketPriorityBadge.tsx
  TicketAttachmentsSection.tsx
hooks/
  useTickets.ts
  useTicket.ts
  useTicketKanban.ts
  useTicketMutations.ts
services/
  ticketService.ts
forms/ ticket-schema.ts
types/ ticket.types.ts
```

### 5. List page

- `Container` + `Breadcrumb` + page title.
- `ListPageToolbar` (search + "Create Ticket" button gated on `tickets.tickets.add`).
- `ListBoardViewToggle` (the existing toggle) - view persisted via `useListBoardViewPreference`. View also reflected in `?view=` for shareable URLs.
- Filters bar: status / priority / category multi-select via `SearchableMultiSelect`, assignee + raised-by via `SearchableSelect` driven by `getUsersSelect`, due-before date filter. Raised-by filter only visible when the user has `tickets.tickets.view_all`.
- **List view** (`TicketsList.tsx`): DataGrid with `tableLayout: { width: 'fixed', columnsResizable: true }`, `columnResizeMode: 'onChange'`. Columns (each with explicit `size`): ticket_number, title (`TruncatedTextCell`), status (`StatusPill` color-driven), priority (`Badge`), category (`Badge variant=secondary`), raised-by (avatar + name), assignee (avatar + name), due_date (red text when overdue), `response_time_hours` (chip - `text-amber-600` if breaching), `updated_at`, actions menu. `listingKey="tickets.tickets.view"`. Row click → detail.
- **Kanban view** (`TicketsKanban.tsx`): five columns (Draft / Submitted / Assigned / Responded / Resolved) using `components/ui/kanban.tsx`. Each card = `Card p-3` with title, ticket_number, priority badge, assignee avatar, due-date with overdue indicator. `onMove` calls `useTicketMutations.changeStatus`; non-assignee/admin cards have `disabled` and a tooltip explaining why.

### 6. Create / Edit modal (`TicketFormDialog.tsx`)
- `FormDialogScaffold` shell + RHF + Zod.
- Fields: title (`Input`), priority (`Select`), category (`Select`), due date (`DatePicker`), description (`RichTextEditor`), attachments (`hooks/use-file-upload.ts` + `uploadAttachment` from the resource-management attachments service with `entityType='ticket'`).
- Footer: `<Button variant="outline">Save Draft</Button>` + `<Button>Submit</Button>` (extends `FormDialogScaffold` with custom footer slot - small enhancement to that component to accept a `footerActions` prop, generic and reused everywhere).
- On success: invalidate `['tickets']` + `toast.success`. On error: `extractApiError` + `toast.error`.

### 7. Detail page - Jira-style + activities panel pinned right

```
[id]/page.tsx
└── <Container>
    └── <Breadcrumb /> Home / Ticket Management / Tickets / TCK-2026-000123
    └── <EntityActivitiesLayout entityType="ticket" entityId={id}>
        └── <TicketDetail />     <-- shrinks left when panel opens
```

`TicketDetail.tsx` is laid out as:

```
┌─────────────────────────────────────────────────────────────────────┐
│ Header strip (Card)                                                 │
│   TCK-2026-000123  [StatusPill][Priority Badge]   [⋯ Actions][< >]  │
│   "Cannot upload screenshot in onboarding flow"                     │
├──────────────────────────────────┬──────────────────────────────────┤
│ MAIN (md:col-span-2)             │ SIDEBAR (md:col-span-1)          │
│ ┌──────────────────────────────┐ │ ┌────────────────────────────┐   │
│ │ TicketSlaStrip               │ │ │ Details                    │   │
│ │  Response: 2h 14m  [✓ in SLA]│ │ │  Status   [StatusPill ▾]   │   │
│ │  Resolution: 5h 02m [⚠ over] │ │ │  Assignee [Avatar ▾]       │   │
│ └──────────────────────────────┘ │ │  Reporter [Avatar]         │   │
│ ┌──────────────────────────────┐ │ │  Priority [Select]         │   │
│ │ Description (rich text)      │ │ │  Category [Select]         │   │
│ └──────────────────────────────┘ │ │  Due date [DatePicker]     │   │
│ ┌──────────────────────────────┐ │ │  Created  2d ago           │   │
│ │ TicketResponseCard           │ │ │  Updated  5m ago           │   │
│ │   [rich text, inline edit]   │ │ ├────────────────────────────┤   │
│ │   "Response by Alice · 2h"   │ │ │ Watchers   [+ Add]         │   │
│ └──────────────────────────────┘ │ │ <AvatarGroup> + remove ×   │   │
│ ┌──────────────────────────────┐ │ ├────────────────────────────┤   │
│ │ TicketResolutionCard         │ │ │ Attachments  [+ Upload]    │   │
│ │   [rich text, inline edit]   │ │ │ list of files              │   │
│ │   "Resolved by Alice · 30m"  │ │ └────────────────────────────┘   │
│ └──────────────────────────────┘ │                                  │
└──────────────────────────────────┴──────────────────────────────────┘
                                          │
                                          ▼
                                   ░░░░░░░░░░░░░░░░░░░░
                                   ░ ActivitiesPanel ░  ← floating launcher
                                   ░ (slides in from   ░    pulses on right
                                   ░  the right edge,  ░    edge until clicked
                                   ░  pushes content   ░
                                   ░  left)            ░
                                   ░░░░░░░░░░░░░░░░░░░░
```

- **Header strip** sticky at top of the scroll container.
- **`TicketSlaStrip`** (new tiny component, reusable): two pills "Response time: 2h 14m" / "Resolution time: 5h 02m". Color: `text-emerald-600` if within SLA, `text-amber-600` if approaching, `text-red-600` if breached. Empty state shows "Awaiting response" / "Awaiting resolution".
- **`TicketResponseCard`** & **`TicketResolutionCard`**: collapsed view shows the rendered HTML + author + relative timestamp; "Edit" button opens an inline `RichTextEditor` with Save / Cancel. Save calls `PUT /tickets/{id}/response` (or `/resolution`), invalidates the ticket, and the SLA strip updates.
- **Right sidebar**: inline-editable Details (Status `StatusPill` opens a popover with allowed transitions, Assignee opens `SearchableSelect` of users, Priority/Category as `Select`, Due date as `DatePicker`), Watchers card with `AvatarGroup` + add via `SearchableMultiSelect` in a popover, Attachments card with dropzone.
- **No comment thread, no history timeline, no tabs in the main column.** All conversational + audit content lives in the floating right-side `ActivitiesNotesPanel`. The launcher pulses (use the existing `shimmering-text.tsx` or a small Tailwind keyframe `animate-pulse`) until first opened on this ticket; after that it's a static icon. A small unread badge can be added later off the back of `ActivityMention` rows.

### 8. Permission gating
`useHasPermission` from `hooks/usePermissions.ts`:
- `tickets.tickets.add` → "Create" button.
- `tickets.tickets.view_all` → raised-by filter visible.
- `tickets.tickets.assign` → assignee picker enabled.
- `tickets.tickets.delete` → delete button visible.
- `tickets.tickets.view` → activities panel mounted (otherwise nothing to mount on, since user can't open the ticket).

---

## Design system / Tailwind component map

The frontend is **Tailwind v4 + shadcn/Radix + Metronic 9 / ReUI** with a rich set of in-house primitives in `components/ui/` and shared scaffolds in `components/common/`. Reuse them - no new design tokens, no off-system colors. Match existing spacing (`px-2.5 py-0.5` for pills, `size-9` for icon buttons, `py-5` for card headers) and color tokens (`text-muted-foreground`, `bg-muted/30`, `border-input`, `text-destructive-foreground`).

### Shared scaffolds (already exist - use directly)
- `components/common/Container.tsx`, `Breadcrumb`
- `components/common/ListPageToolbar.tsx`
- `components/common/ListBoardViewToggle.tsx` + `hooks/useListBoardViewPreference`
- `components/common/StatusPill.tsx`
- `components/common/SearchableSelect.tsx`, `SearchableMultiSelect.tsx`
- `components/common/FormDialogScaffold.tsx` (extend with `footerActions` slot for Save Draft + Submit)
- `components/common/ConfirmDeleteDialog.tsx`
- `components/common/DetailActionsMenu.tsx`
- `components/common/RecordNavigation.tsx`
- `components/common/TruncatedTextCell.tsx`
- `services/userSelectService.ts` (`getUsersSelect`)

### UI primitives (already exist)
- DataGrid suite (`data-grid.tsx`, `data-grid-table.tsx`, `data-grid-column-header.tsx`, `data-grid-pagination.tsx`, `data-grid-columns-panel.tsx`, `data-grid-column-filter.tsx`)
- `kanban.tsx` (dnd-kit)
- `rich-text-editor.tsx` (Tiptap - extend with @-mention extension for the activities composer)
- `tabs.tsx`, `toggle-group.tsx`, `card.tsx`, `dialog.tsx`, `popover.tsx`, `tooltip.tsx`, `select.tsx`, `date-picker.tsx`, `avatar.tsx`, `avatar-group.tsx`, `badge.tsx`, `button.tsx`, `input.tsx`, `textarea.tsx`, `skeleton.tsx`, `separator.tsx`, `scroll-area.tsx`, `alert-dialog.tsx`, `alert.tsx`, `file-upload.tsx`, `form.tsx`, `sonner.tsx`

### Icons (lucide-react, already a dep)
`LifeBuoy` (sidebar group + footer), `Plus` (create), `Filter`, `LayoutList`/`LayoutGrid` (toggle), `Paperclip`, `Smile`, `AtSign` (mention prompt), `Activity`/`HeartPulse` (activities tab + launcher), `FileText` (notes tab), `MessageSquare` (messages tab), `Clock` (SLA), `AlertCircle` (urgent), `User`, `MoreVertical`, `X`.

### What we do NOT add
- No new dialog/modal primitives - `FormDialogScaffold` + `ConfirmDeleteDialog` cover everything.
- No new kanban library, no new rich text editor, no new toast library.
- No new Tailwind plugin or design tokens.

---

## Critical files to create

### Backend
- `app/modules/activities/{__init__.py,bootstrap.py,manifest.py}` - DONE
- `app/modules/tickets/{__init__.py,bootstrap.py,manifest.py}` - DONE
- `app/models/{activities.py,tickets.py}` - DONE
- `app/schemas/{activities.py,tickets.py}` - DONE
- `app/services/{activities_service.py,activities_registry.py,tickets_service.py}` - TODO
- `app/api/v1/activities/{__init__.py,activities.py}` - TODO
- `app/api/v1/tickets/{__init__.py,tickets.py}` - TODO
- `alembic/versions/{166_create_activities_module.py,167_create_tickets_module.py,168_seed_tickets_rbac.py}` - TODO

### Backend modify
- `app/api/v1/__init__.py` - mount both routers.
- `app/services/list_query_registry.py` - register tickets adapter.
- `app/rbac/permission_registry.py` - add ticket perms.
- `app/main.py` - register tickets adapter into `ACTIVITIES_REGISTRY` on startup.

### Frontend
- `components/common/ActivitiesNotesPanel/` (full tree listed above) + `EntityActivitiesLayout.tsx`
- `app/(protected)/ticket-management/tickets/` (full tree listed above)

### Frontend modify
- `app/components/layouts/demo10/components/footer.tsx` - replace Support href.
- `config/menu.config.tsx` - add Ticket Management entry.
- `components/common/FormDialogScaffold.tsx` - accept optional `footerActions: ReactNode` slot.
- `components/ui/rich-text-editor.tsx` - accept an optional `mentionUsersFetcher` prop to plug in @-mentions; default is no mention extension (zero impact on existing call sites).

### Reuse - do not duplicate
- `app/services/entity_attachment_service.py`, `app/services/storage_router.py`
- Existing Respond.io call paths in `app/api/v1/external/respond_contacts.py` + complaint conversation code (factor `ComplaintConversationPanel`'s message-bubble renderer into a tiny shared `RespondMessageBubble`).
- `lib/api-client` (`extractApiError`, `buildDataGridParams`)
- `hooks/usePermissions.ts`, `hooks/use-file-upload.ts`
- `app/(protected)/resource-management/attachments/services/attachmentService.ts` (`uploadAttachment`)

---

## Verification

### Backend
1. `alembic upgrade head` - three new migrations apply cleanly.
2. `pytest tests/test_rbac.py -q` - existing RBAC tests still pass.
3. New unit tests:
   - `tests/test_activities_service.py` - post activity, post note (private), system event recording, mention writes `ActivityMention` row.
   - `tests/test_tickets_service.py` - visibility filter for non-admin, status transition validation, response/resolution updates flip status + set SLA durations, watchers toggle.
4. Manual smoke: with both JWT and `X-API-Key`, hit list / kanban / detail / status / response / resolution.

### Frontend (Playwright MCP - required per CLAUDE.md)
With BE :8000 and FE :3000 running:
1. `browser_navigate /` → click footer **Support** → lands on `/ticket-management/tickets` empty state.
2. **Create**: click "Create Ticket" → fill title/priority/category, type rich text with bold + list, drop a screenshot → Submit. New row appears in DataGrid; `browser_network_requests` shows `POST /tickets-management/tickets` then `POST /attachments`.
3. **Detail**: click row → header strip + SLA strip ("Awaiting response") + description + empty Response card + empty Resolution card + sidebar with status/assignee/priority/due/watchers/attachments, all rendered. Pulse-icon launcher sits on the right edge.
4. **Activities panel**: click launcher → main content shrinks left, panel slides in (no overlay). Activities tab shows the system "TCK-…-000001 created" event. Switch to Internal Notes tab → "No internal notes yet." Switch to Messages tab → submitter's Respond contact pre-selected (when phone matches) or "Choose a contact to reply." prompt.
5. **Post update + auto-status**: log in as the assignee, open the ticket (now `assigned`), in Activities tab type "Working on it" → Post. Expect: feed shows the new entry, ticket status flips to **Responded** in the sidebar pill, SLA strip shows a response duration in green, a system event "Status changed Assigned → Responded" appears in the feed.
6. **Response field**: as assignee, click "Edit" on the Response card → write rich text → Save. Card renders the saved HTML + "Response by … · just now". `responded_at` and `response_time_hours` populated.
7. **Resolution + Kanban**: switch to board view → drag the card from Responded to Resolved. Card moves; SLA strip's resolution duration populates; sidebar status pill updates.
8. **Visibility**: log in as a third unrelated non-admin → list page is empty; direct-navigating to the ticket id from step 2 returns 404.
9. **Mentions**: in the Activities composer type "@al" → mention popup populated by `getUsersSelect`. Pick "Alice" → submit → backend writes `ActivityMention`; the mentioned user gets the activity in their notifications (notification wiring is generic / out-of-scope here, but the row exists).
10. **Delete**: as admin, click delete in `DetailActionsMenu` → `ConfirmDeleteDialog` "Delete ticket?" / "This action cannot be undone." → confirm → row removed.
11. **Resizable columns + persistence**: drag a column edge → reload → width persists (uses `listingKey="tickets.tickets.view"`).
12. `browser_console_messages` - no errors/warnings throughout.
13. **Mobile**: toggle the device emulator to a phone width → activities panel takes the full width when open, the launcher stays positioned on the right edge when closed.
