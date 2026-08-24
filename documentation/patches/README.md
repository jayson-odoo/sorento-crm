# Phase 3 manual step - add Ticket Management to the sidebar

The sidebar layout reads `config/menu.config.tsx` directly (not the
`@/modules/registry` discovery loader, which is exported but not yet
wired up in `app/components/layouts/`). The file is 70 KB and a single
tool-call inline edit was deemed expensive, so the change is shipped
as a small patch instead.

**Apply once, from repo root:**

```bash
git apply documentation/patches/add-ticket-menu-entry.patch
```

This adds the same 11-line block to two places - `MENU_SIDEBAR` and
`MENU_SIDEBAR_COMPACT` - right above the existing `Complaint Management`
entry, so both layouts stay aligned. `LifeBuoy` is already imported in
that file.

After applying, restart the FE dev server (`pnpm dev` / `npm run dev`)
and the new "Ticket Management → Tickets" link will be visible.

The footer Support link has already been rewired in the same commit
that shipped this patch, so it lands on `/ticket-management/tickets`
as soon as that page exists (Phase 3b ticket pages).
