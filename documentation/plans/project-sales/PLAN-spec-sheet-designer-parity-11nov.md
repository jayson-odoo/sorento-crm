# PLAN: spec sheet designer parity with the price tag designer

Status: Slice A in build (small fix track: FE only, no migration, no auth/RBAC change). Slice B is a
behaviour card waiting on the owner; no code for it until answered.

Lane: SPEC-SHEET-DESIGNER-PARITY. Owner feedback 11 Nov 2026 (spec sheet SS1 Draft).

## Slice A (fixes)

1. "Add accessory" options show the code once (code + name only when they differ), fixed in the
   shared option label builder.
2. Clipboard parity: Cmd/Ctrl+C / X / V / D and context-menu Paste work in the spec sheet designer
   as in the price tag designer (elements and OS-clipboard images).
3. Resizable Pages and Inspector panels, same component/behaviour as the template designer.
4. Insert field: `{{product.description}}`.

Acceptance criteria: `spec-sheet-designer-parity-11nov-acceptance-criteria.md`.

## Slice B (card first)

Variable registry, several products on one page, table element, PowerPoint export. Card posted
as a `crew-ask` on the PR; built only after the owner answers.
