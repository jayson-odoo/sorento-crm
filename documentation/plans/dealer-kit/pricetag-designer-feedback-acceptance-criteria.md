# UAC: price tag designer feedback (14 Nov)

Plan: `PLAN-pricetag-designer-feedback-14nov.md`. Slice 1 = AC-2, AC-4, AC-9. Slice 2 = AC-1, AC-3, AC-5..8 (after the owner answers the behaviour card).

## Slice 1

### AC-2 Description indents are kept
- AC-2.1 Rich text `<p>Basin size:</p><p>   L580xW450xH450mm</p>` laid out by `richLayerLines` (lib/dealer-kit/text-layout.ts): line 2 starts with a space piece of 3 spaces' width, so its first word starts right of x=0 (measured canvas) and its text begins with "   " (no measure).
- AC-2.2 Leading spaces right after a hard break (`<br>` / "\n") are kept the same way.
- AC-2.3 Spaces at a soft wrap (a long line that wraps on its own) are still dropped: the wrapped line starts with its word, not a space. Spaces between words are unchanged.
- AC-2.4 Plain (non-rich) text with leading spaces after "\n" keeps them the same way, if the plain path drops them today.
- AC-2.5 The shared `RichTextEditor` keeps leading and repeated spaces when content is loaded: mount it with `<p>   L580</p>`, the editor's HTML still holds the 3 spaces (as spaces or &nbsp;), and an untouched editor does not emit a change that strips them.
- AC-2.6 The backend sanitiser (`tag_rich_text.py`) keeps leading spaces and `&nbsp;` in a description round trip.

### AC-4 Insert field while previewing
- AC-4.1 Browser check: on a template with a sample product previewing, select a text box, Insert field inserts `{{...}}` at the cursor. Reported in the browser-pass note; no code change if it works.
- AC-4.2 (owner hand test 14 Nov ~22:00) With the rich Content editor open holding "{{combo.description}}" (paragraph 1) and bold "LP: RM {{product.list_price}}" (paragraph 2) and the caret after "RM ", Insert field opens with the Content box showing the element's EXISTING text (both lines, tokens as written; never empty) with the insert point visible at the caret.
- AC-4.3 Picking a field shows it at the caret in the dialog's Content box; the Preview renders the whole content (before + field + after) against the previewed data, so it is never empty when data exists; with no data it shows the existing "(preview a product to see values)" text.
- AC-4.4 Done inserts only the picked field(s) at the rich editor's caret: the stored HTML keeps paragraph 1 and the bold run of paragraph 2 (`<strong>` around "LP: RM " and the new token sits at the caret inside it); nothing else in the content changes. Picking two fields inserts both, in order, at the caret.
- AC-4.5 Cancel changes nothing. Without the rich Content editor open (Inspector Insert field on a plain layer), the dialog behaves as today (editable content, Done replaces the content).

### AC-9 Crop (shared TagCanvasEditor: price tag template editor + spec sheet designer)
- AC-9.1 While dragging a crop handle or the crop window, the drawn source picture keeps the same position and scale on every move (only the window changes); the handle stays under the pointer.
- AC-9.2 Dragging the crop window right by d moves the crop rect right (cropRect.x increases) and the picture does not move.
- AC-9.3 The crop view loads the same image URL as the layer itself renders (`displayFor`), including icon library images.
- AC-9.4 During crop the real image layer does not take clicks or drags (listening off / not draggable), so a click outside the window commits.
- AC-9.5 After Done the layer's opacity is back to 1 (explicitly, not undefined) and the image draws with the new cropRect.
- AC-9.6 Esc / Cancel restores the previous cropRect.
