# Price Tag Designer Round 6 - acceptance criteria

Plan: `PLAN-price-tag-r6.md`

## Journey

**Actor:** the marketing designer (Dealer Kit manage permission). Two entry points, same canvas.

**A. Request designer.** Arrives from sidebar Dealer Kit > Price Tag Requests > a request in
`designing` > Design Price Tags. First screen: LINES rail with every line already carrying a
tag cloned from its family's template (the system knows the product, price, family, template
and size; nothing is asked). They click a line, adjusts the design: nudges a layer with arrow
keys (decision: how far, expressed by which modifier), rotates a strip with Shift to a clean
angle and reads the angle as they go, crops the black bar off a product photo, resizes a
slanted price box by its corners then reshapes a corner on double-click. They copy the price
group from this line and pastes it on the next line. They shrink a tag and sees the price
group hanging off the edge, dimmed, and drags it back in. Satisfied, they open the toolbar's
Template menu and picks **Update "DIY Tag"**; the dialog says which version it will publish
and offers to push the design to the two other lines on this template (one decision, default
on). At the end they hold: a request whose lines share the corrected design, and a template
whose next pick anywhere gets it. They click the one button in the header, **Mark proof
ready**. Automatically: the dealer's portal shows the proof; the template's Versions sheet
records "Updated from PT-202609-0001".

**B. Template editor.** Arrives from Dealer Kit > Tag Templates > a template. Same canvas,
same tools. The one thing they could not do before: change the tag's size after creating it.
The Tag Size control sits where it sits in the request designer. Header holds one button,
**Publish**.

Decisions the user makes: modifier for nudge step, Shift or not on rotate, where to crop,
which mode on a polygon, update-or-save-as on the Template menu, sibling checkbox. Everything
else is derived.

**Phases.** Phase 1 (FE, mocked): every slice; S1 and S6 against a mocked
`tagTemplateService`. Phase 2 (BE wiring, test-first): no new routes; S1 swaps the mock for
the existing PUT with `print_size`, S6 for PUT + publish; vitest for every slice lands here.
Phase 3: review.

Every AC holds in BOTH editors (template editor and request designer) unless it names one.
Browser evidence at 1280 and 375 unless the AC is keyboard-only. Tags: `[FE]` component or
hook, `[BE]` backend, `[E2E]` real clicks against the running stack, `[T]` unit-testable pure
logic.

## S1 tag size on templates
- AC-S1-1 [FE] Template editor shows the same Tag Size control as the request designer (preset dropdown, W/H mm) in the left rail; no "Apply to all lines".
- AC-S1-2 [FE] Changing W or H resizes the artboard live without remounting the editor (a focused input keeps focus, selection is kept).
- AC-S1-3 [E2E] Save (or autosave) then reload shows the new size; the templates list Print size column shows it; a request that picks the template afterwards gets the new size.
- AC-S1-4 [T] A value below the 10 mm floor is clamped with the same error text as the request designer.
- AC-S1-5 [T] Layers are not moved or scaled by the resize.

## S2 nudge
- AC-S2-1 [FE] Arrow moves the selection 0.25 mm; Shift+Arrow 1 mm; Alt/Option+Arrow 0.1 mm. Inspector X/Y reflect the exact value.
- AC-S2-2 [FE] Inspector X/Y/W/H spinners step 0.25 mm.
- AC-S2-3 [T] A locked layer does not move; a group moves once with its children.

## S3 clipboard across lines and pages
- AC-S3-1 [E2E] Request designer: copy layers on line A, click line B, paste: the layers appear on line B at the same X/Y as on A.
- AC-S3-2 [E2E] Copy in the template editor, navigate to a request's designer, paste: the layers appear on the selected line's tag.
- AC-S3-3 [T] Paste on the same tag or template still offsets by 5 mm as before.
- AC-S3-4 [FE] Cut works the same way across lines. A page reload empties the clipboard (paste is disabled).
- AC-S3-5 [T] The clipboard never leaves the browser tab: no network call, no localStorage or cookie write on copy or paste; another user (or another tab) cannot paste what this user copied.

## S4 ghost layers
- AC-S4-1 [FE] After shrinking a tag, a layer that now lies past the edge is drawn at 30% opacity outside the artboard, and can be clicked, dragged back inside, and transformed.
- AC-S4-2 [FE] A layer partly outside shows its inside part at full opacity and its outside part ghosted, with one selection box.
- AC-S4-3 [FE] Layers panel rows for such layers show the "outside" marker; dragging the layer inside removes it.
- AC-S4-4 [E2E] The printed PDF does not show the ghosted part (unchanged clipping).
- AC-S4-5 [T] Fully inside layers render exactly as before (single pass, no double draw).

## S5 polygon modes
- AC-S5-1 [FE] Single-click on a polygon shows the Transformer with all 8 resize anchors and rotate; no corner/edge handles. Dragging an anchor resizes the polygon, shape proportions preserved by the normalised points.
- AC-S5-2 [FE] Double-click (or Enter on the selection, or Inspector "Edit points") enters edit-points mode: anchors gone, vertex + edge handles shown; dragging them reshapes as in r5, Shift lock included.
- AC-S5-3 [FE] Esc, Enter, clicking empty canvas, or selecting another layer exits edit-points mode.
- AC-S5-4 [FE] A boxed list-only price badge follows the same two modes.
- AC-S5-5 [T] A locked or hidden polygon offers neither mode.

## S6 update template
- AC-S6-1 [FE] Request designer, tag cloned from template T: the toolbar Template dropdown shows "Update T" and "Save as new template". A tag whose template was deleted shows only "Save as new template".
- AC-S6-2 [FE] "Update T" opens a confirm dialog naming T and the next version number, with the sibling checkbox only when at least one other line uses T (count shown), default on.
- AC-S6-3 [E2E] Confirm publishes a new version of T with note "Updated from <doc_number>"; the template's Versions sheet lists it; a new request picking T gets the updated design and size.
- AC-S6-4 [E2E] With the checkbox on, every other line using T in this request gets the design and size; lines from other templates are untouched; the undo toast reverts the siblings only.
- AC-S6-5 [T] With the checkbox off, sibling lines are unchanged.
- AC-S6-6 [FE] Cancel changes nothing.

## S7 one CTA
- AC-S7-1 [FE] Request designer (designing state): the request bar right side holds the Saved indicator and exactly one button, "Mark proof ready". Full screen, Template dropdown and Save sit at the right end of the canvas toolbar.
- AC-S7-2 [FE] Template editor: the page header holds the Saved indicator, "Publish" as the only action button, and Back to templates. Versions, Save and Full screen sit at the right end of the canvas toolbar.
- AC-S7-3 [E2E] At 375 px both toolbars are reachable without clipping (horizontal scroll or overflow menu); the request bar fits one row.
- AC-S7-6 [FE] The moved actions render as toolbar icon buttons (same size, spacing, hover and tooltip pattern as the tool groups on the left), forming one group at the right end; no outlined text buttons in the toolbar.
- AC-S7-4 [E2E] Every moved action still works (Full screen toggles the shell, Save flushes autosave, Versions opens the sheet).
- AC-S7-5 [FE] Arrange mode hides the Template dropdown as it hid Save as template before.

## S8 crop
- AC-S8-1 [FE] Right-click on an image layer offers "Crop image"; double-click on an image does nothing (no crop entry).
- AC-S8-2 [FE] Crop mode shows the whole source dimmed with a bright crop window and 8 handles; handles cannot leave the source; dragging inside pans the window.
- AC-S8-3 [FE] Enter or clicking outside commits; the layer now shows only the cropped region, fitted per the layer's fit setting; Esc restores the previous crop.
- AC-S8-4 [E2E] The printed PDF shows the same cropped region as the canvas, for contain, cover and stretch, and with the circle mask.
- AC-S8-5 [FE] Inspector shows "Reset crop" only when a crop is set; it restores the whole image.
- AC-S8-6 [T] A template saved before this round (no cropRect) renders exactly as before.

## S9 rotation
- AC-S9-1 [FE] Rotating with Shift held snaps to 15-degree steps; releasing Shift mid-drag frees the angle; pressing it mid-drag snaps again.
- AC-S9-2 [FE] While rotating, a label near the rotate handle shows the angle (one decimal free, integer snapped); it disappears on release. Inspector rotation shows the same value.
- AC-S9-3 [FE] Shift on a corner anchor keeps the aspect ratio; side anchors are unaffected; text still reflows to the new width.

## S10 context menu on images
- AC-S10-1 [FE] Right-click on an image layer (selected or not) opens the layer menu (Cut, Copy, Paste, Duplicate, Crop image ...), never the empty-canvas menu.
- AC-S10-2 [FE] Right-click on empty canvas still opens Paste / Select All / Fit to View / Zoom 100%.
- AC-S10-3 [T] The reproduced cause is named in the PR description with the failing case as a test.
