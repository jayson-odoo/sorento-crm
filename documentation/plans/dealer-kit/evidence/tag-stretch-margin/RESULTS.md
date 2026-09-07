# Browser verification: image Stretch fit + price badge Margin + Show currency

Stack: FE http://localhost:3100, BE http://localhost:8110 (captain-owned, not started/stopped by this run).
Tool: `agent-browser@0.27.0`, `--session stretch-margin-verify`.
Test artifact: template "ZZT Verify Stretch" (created via New Template, deleted at end via the
10s deferred-delete countdown, allowed to lapse). No other template was edited or saved.

## Per-AC results

- **AC-1** Fit dropdown offers Cover/Contain/Stretch. PASS. `08-picked-image.png`, dropdown opened
  with all three options confirmed in the accessibility tree.
- **AC-2** Stretch fills the box, distorted, no letterbox/crop. PASS. `15-stretch-w60h80.png` /
  `16-stretch-clean.png` on a 60x80mm box: image fills edge-to-edge, visibly distorted vs the
  Cover/Contain renders of the same box.
- **AC-5** Cover crops (no letterbox), Contain letterboxes (no crop) - unchanged. PASS.
  `10-contain-w60h80.png` (white bars top/bottom) vs `14-cover-full-view.png` (fills box, crops
  content, no white bars) on the identical 60x80mm box/image.
- **AC-6** Price badge inspector shows `Margin (mm)` group above `Padding (mm)`. PASS. Confirmed
  in DOM order (`20-scroll1.png`) and again on the legacy "Bathroom Furniture Tag" badge.
- **AC-7** Margin insets the callout independently of Padding (which insets the figure from the
  callout). PASS, verified with a REAL bound product (2102AW, list price RM19) so the callout
  actually renders (an unbound "Price TBC" placeholder never draws the callout box - not a defect,
  same behaviour on the pre-existing "Bathroom Furniture Tag" template). Screenshots:
  `30-margin2-padding1.png` (callout inset 2mm, flush text-ish at 1mm), `31-margin4-padding0.png`
  (callout inset further to 4mm, text flush to callout edge), `32-margin0-padding3.png` (callout
  back flush to the layer box - margin=0 - only the padding value changed). The callout's own
  inset visibly tracks Margin only; it does not move when only Padding changes.
- **AC-9 / AC-10** Legacy badge (padding set pre-feature, no margin) renders identically and a
  same-value edit doesn't jump. PARTIAL / not fully provable. Read-only inspected the only
  pre-existing badges available: seeded "Bathroom Furniture Tag" (Live v1) - Margin and Padding
  both show 0/0/0/0 (`22-legacy-template.png`), a degenerate case (no non-zero legacy padding
  exists in this environment to migrate). Did not touch its fields (never edit/save a template not
  created by this run). Could not exercise the actual padding-to-margin migration with real
  numbers without editing someone else's template or fabricating DB rows, so AC-9/AC-10 are
  confirmed only for the trivial 0/0 edge case, not a real non-zero legacy value.
- **AC-12** Inspector usable at 375px and 1280px. **FAIL at 375px.** At 1280px the Inspector
  renders normally and both groups scroll into view uncut (`40-1280-inspector.png`). At 375px the
  entire `INSPECTOR` panel is absent from the DOM (not just clipped/overflowing - `grep -i
  inspector` on the full accessibility snapshot returns nothing), confirmed on two screenshots
  (`38-375-viewport.png`, `39-375-scrolled.png` - page ends at the footer with no Inspector at
  all). Layer selection and canvas still work at 375px; only the property panel is unreachable, so
  Margin/Padding cannot be edited at that width. Not something this feature specifically broke in
  isolation (the whole Inspector vanishes, not just the new Margin group), but the AC explicitly
  requires 375px usability and it is not met.
- **AC-13 / AC-14** `Show currency` checkbox, on by default, drives `RM` prefix. PASS.
  `29-box-on-real.png` (checked, "RM 19") -> `33-currency-off.png` (unchecked, "19") ->
  `35-promo-nocurrency.png` (switched Variant to "Promotion (LP struck + SP)", still unchecked,
  still no RM) -> `36-promo-currency-restored.png` (re-checked, "RM 19" back). Both variants
  confirmed to honour the flag.
- **AC-16** Stretch + margin + currency-off persist through reload. PASS. Set Image fit=Stretch,
  Margin=2/2/2/2, Padding=3/3/3/3, Show currency=off, clicked Save, then full page reload
  (`open` on the same URL, not SPA nav). `37-reloaded.png` plus field reads after reload confirm
  all three: Fit combobox = "Stretch", Margin spinbuttons = 2/2/2/2, Padding = 3/3/3/3, Show
  currency checkbox = unchecked, canvas reads "19" (no RM).
- **AC-3 / AC-8 (print agreement)** SKIPPED. The only preview affordance found is "Preview this
  block with <product>" (`41-preview-click.png` / `42-preview-result.png`), which re-renders the
  same Konva canvas with a bound product - not the print/PDF page (`TagSheetRenderer`). Reaching
  an actual print render requires the Price Tag Requests flow (create a request, bind a real SPO/
  product, generate) - more than a "few clicks" per the brief's own skip condition, so this was
  not attempted.

## Console / errors

`console` showed only pre-existing/unrelated noise (React Fast Refresh logs, a `Demo1Layout` "key
prop" warning, and a `DialogContent` missing-description a11y warning on modals) - nothing tied to
Stretch, Margin, or Show currency. `errors` returned nothing (no uncaught exceptions) throughout.

## Cleanup / end state

- Created template "ZZT Verify Stretch" (id `56ce5e4c-9cb0-4694-90fc-e0f22ee9bb08`), deleted via
  the row's Delete action; the 10s countdown was allowed to lapse (not cancelled). Confirmed gone
  from the Tag Templates list (`44-cleanup-confirmed.png`): only "Bathroom Furniture Tag" (Live
  v1) and "S1 Verify Template" (Draft, pre-existing, not created by this run) remain.
- Opened two pre-existing templates read-only for AC-10 comparison ("Bathroom Furniture Tag",
  briefly "S1 Verify Template" which turned out to have no layers) - neither was edited or saved.
- Session `stretch-margin-verify` closed (not `--all`).

## Defect summary

1. **AC-12 FAIL** - Inspector panel (and therefore the new Margin/Padding groups) is not present
   at all at 375px viewport width in the tag template editor. Repro: open any tag template editor,
   select any layer, `set viewport 375 812` - the right-hand Inspector column disappears entirely
   (Layers + Canvas remain). Not new damage from this feature specifically (the whole panel is
   gone, not just the new fields) but the UAC calls out 375px usability explicitly and it fails.
