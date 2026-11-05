# PLAN: spec sheet page editor UX (full screen, collapsible panels, Apply-to control)

Status: in progress (small fix track: FE only, no migration, no auth/RBAC change)

Lane: SPEC-SHEET-EDITOR-UX. Owner ask, 5 Nov 2026: full-screen the spec sheet page editor like the
price tag designer, collapsible left (pages) and right (Inspector) panels, and explain why his
"Project Page Default Template" does not show on SS1.

## Scope

1. Full screen toggle on the spec sheet reader, reusing `FocusShell` + `FocusToggle`
   (`app/(protected)/dealer-kit/components/FocusMode.tsx`), the same pair the price tag
   designer (`RequestTagDesigner.tsx`) and the tag template page use.
2. Left page rail and right Inspector fold away with `CollapsiblePanel` from the same file
   (the room designer and page builder's own fold control).
3. Inspector "Apply to" becomes a two-option segmented control: "This page | Every page".
   Behaviour unchanged.
4. Template choice: see acceptance criteria file and the crew-note on the PR.

Acceptance criteria: `spec-sheet-editor-ux-05nov-acceptance-criteria.md`.
