# PLAN: TOGGLE-SELECTED - the selected toggle option is the primary colour app-wide

Status: Implemented, in review #1789 (small fix track: FE-only, no migration, no auth/RBAC change, expected diff under 300 lines)

## Owner's words (20 Oct 2026)

"i need you to do a full system audit to make sure for all the toggle component, the one selected should be in main
background colour, colour like the screenshot is not acceptable cause look very similar"

Screenshot: Contact Tag settings, Chatbot section, "Not set | On | Off" segmented toggles. The selected segment is light
grey and reads the same as the unselected ones; the Switches above it are already primary blue.

## Root cause

- `sorento_crm_frontend/components/ui/toggle.tsx:9` `toggleVariants` paints the selected state
  `data-[state=on]:bg-accent data-[state=on]:text-accent-foreground`.
- `--accent` is `zinc-100` (`css/config.reui.css:17`), a hair darker than the white of the unselected segments, so the
  selected option is close to invisible. `ToggleGroupItem` (`components/ui/toggle-group.tsx`) reuses `toggleVariants`,
  so every `ToggleGroup` in the app inherits it.
- The Switch already uses the primary token for its on state (`components/ui/switch.tsx:46`
  `data-[state=checked]:bg-primary`), which is the target look.

## Fix

1. `toggleVariants` selected state becomes `data-[state=on]:bg-primary data-[state=on]:text-primary-foreground`
   (the Switch's token), with a visible hover on the selected item (`bg-primary/90`) and the existing focus ring and
   `disabled:opacity-50` kept, so a disabled selected item is still distinct. No new colours.
2. Call sites that override the selected state inline with a non-primary colour (e.g. `data-[state=on]:bg-background`)
   lose the override so they inherit the shared rule. Hand-rolled segmented controls that style their own selected state
   with a non-primary colour move to the same tokens (or to `ToggleGroup`).
3. Keyboard / ARIA behaviour unchanged: Radix still owns `data-state`, `aria-pressed` / `aria-checked` and roving focus.

In scope after the audit: pill (`variant="default"`) and `button` tab strips, which DESIGN-LANGUAGE.md section 4 reserves
for view toggles. Line tabs are navigation and stay as they are.

## Acceptance criteria

- AC-1: a selected `Toggle` / `ToggleGroupItem` (default and outline) is `bg-primary` with `text-primary-foreground`;
  unselected options keep their plain style. Contact Tag settings' Not set | On | Off is the reference screen.
- AC-2: hovering a selected option keeps it primary (`bg-primary/90`) with white text; hovering an unselected one shows
  the existing grey. Focus ring unchanged; a disabled selected option is still dimmed (`disabled:opacity-50`).
- AC-3: a pill (`variant="default"`) or `button` tab strip shows its active option primary with white text and icon;
  line tabs keep the primary underline and no fill.
- AC-4: no call site overrides the selected fill with a non-primary colour or a faint tint; every hand-rolled toggle in
  the audit selects with the same tokens (or Button `variant="primary"`). Content inside a selected option (the
  quotation scope chip's $ button) stays readable at rest, on hover and while open.
- AC-5: keyboard and ARIA unchanged (`data-state`, `aria-pressed` / `aria-checked`, roving focus); no layout change and
  no horizontal scroll at 375 on the verified screens.

## Tests (red first)

- `components/ui/toggle.selected.test.tsx`: a selected `ToggleGroupItem` (both variants) and a pressed `Toggle` carry
  `data-[state=on]:bg-primary` + `data-[state=on]:text-primary-foreground` and no `data-[state=on]:bg-accent`.
- Inventory guard: no `.tsx` under the app overrides the toggle's selected state with a non-primary background
  (`data-[state=on]:bg-(background|accent|muted|...)`).
- Call-site tests for any component fixed beyond the primitive (ListBoardViewToggle and similar).

## Verification

agent-browser 1280 + 375 on Contact Tag settings plus at least 4 other screens from the audit, before/after
screenshots in the PR crew-note.

## Audit

Posted as a crew-note table on the PR.
