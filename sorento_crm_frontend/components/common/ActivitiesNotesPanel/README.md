# ActivitiesNotesPanel

Generic per-entity right-side panel mounted on detail pages. Three tabs:
Activities (chronological feed of system + user_update events),
Internal Notes (private to current user), Messages (Respond.io contact
thread, currently stub-backed).

## Usage

```tsx
import ActivitiesNotesPanel from '@/components/common/ActivitiesNotesPanel';

// In a detail page (after the entity is loaded):
<ActivitiesNotesPanel entityType="ticket" entityId={ticket.id} />
```

The component renders a floating red pulse-icon launcher pinned to the
bottom-right; clicking opens a Radix Sheet from the right edge.

## Backend dependency

Every route is `(entity_type, entity_id)`-keyed. Each consuming module
registers an adapter on backend startup in `app/main.py` via
`register_activities_adapter(...)` so the activities service knows how
to check visibility, look up Respond.io contacts, and run on_post
side-effects (e.g. for tickets, auto-flip `assigned -> responded` when
the assignee posts a chat message).

For tickets the adapter is `entity_type="ticket"` (already registered).

## Known cuts vs the spec (intentional, follow-ups queued)

- **Layout**: uses `Sheet` overlay rather than `EntityActivitiesLayout`
  (push 420 px column). Functional parity; visual cut. The push-layout
  primitive lands as a follow-up; consumers won't have to change props.
- **Composer**: plain `Textarea`, not `RichTextEditor` with @-mention
  popup. The schemas already pass `mentioned_user_ids` so the FE can
  upgrade without touching the API.
- **Messages tab**: backend is stubbed (returns empty page; outbound
  send writes a `message.sent` system Activities row but doesn't hit
  Respond.io). Real proxy is Phase 4.
- **Attachments**: `attachment_ids` on the post-activity payload is
  reserved but the composer does not yet expose a paperclip + dropzone.
  Wires up alongside the rich-text editor swap.
