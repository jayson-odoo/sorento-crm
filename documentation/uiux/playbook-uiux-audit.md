# Foundryx UI/UX playbook: gap audit of the Sorento CRM frontend

Lane UIUX-PLAYBOOK-AUDIT, 10 Nov 2026. Read-only: no app code, no mock, no root `playbook-uiux.md`
(that file means "playbook applied" and waits for the owner's answers to the questions in section 6).

- **Playbook audited against:** `foundryxkay/playbook-UIUX` at `c7dfb32`, skill
  `skills/foundryx-playbook-uiux/SKILL.md` (cited below as `PB:<line>`), `knowledge/decisions.md`,
  and `reference/clarity-draft.html` (cited as `draft:<line>`).
- **Steps done:** "First time on a system" steps 2 and 3 only (`PB:12-25`).
- **Not run:** `scripts/ui-audit.cjs`. A real product needs its own `--app` adapter (`PB:57`); building
  one is code, out of scope for a read-only lane.

## 1. Step 2 verdict

**Existing system:** 469 protected pages (`app/(protected)/**/page.tsx`), 154 shared primitives in
`components/ui/`, Metronic 9 + ReUI shell, Tailwind 4, and its own binding design contract
(`PRINCIPLES.md` "Design mandates", `documentation/reference/DESIGN-LANGUAGE.md`,
`documentation/reference/ADR-PRODUCT-STANDARDS.md`, `documentation/reference/PR-CHECKLIST.md`).
So this is a gap audit, and every playbook rule lands on a screen that already has a rule of its own.

## 2. Owner rules that win, and where the repo records them

From the lane brief (owner + management, 9 Nov). Several live only in crew memory, not in the repo's
design docs; writing them into `DESIGN-LANGUAGE.md` is quick win 10.

| Owner rule | Recorded in repo | Code today |
| --- | --- | --- |
| Every date dd/mm/yyyy via one shared formatter | No dd/mm clause; nearest `DESIGN-LANGUAGE.md:199`, `PRINCIPLES.md:296` (formatDateTimeInMalaysia on raw strings) | dd/mm/yyyy yes, but six helpers in `lib/helpers.ts` (`formatDate:128`, `formatDateSafe:187`, `formatDateInMalaysia:325`, `formatDateTimeInMalaysia:446`, `formatDateRange:469`, `formatDateTime:499`), plus about 52 bare `format(` calls (rough grep) |
| Lists = standard DataGrid, one line per row | Not found; nearest `DESIGN-LANGUAGE.md:156` (fixed layout, truncate + title) | One line, with one exception on OI list (`H:497-510`, Reserve cell stacks a badge and a "parked by" line) |
| All columns sortable server-side | Not found | OI list: all but Reserve (`H:491`) |
| All dropdown filters multi-select | `ADR-PRODUCT-STANDARDS.md:43` (component), not framed as a filter rule | OI list: Raised by, Agent, Project multi (`H:681,705,718`); Reserve single (`H:665`) |
| Grid select like Odoo | Not found | Shift+click, drag and Shift+Arrow ranges (`UI/data-grid-range-select.ts:8-21`) |
| UI minimal; lightbox/dialog over side panels | Partly: `DESIGN-LANGUAGE.md:159` (Dialog/Sheet/AlertDialog are lightbox surfaces) | Mostly dialogs; one Sheet on price tag (`RequestDesignSection.tsx:23,232`) |
| Right-click menus over row icons | Not found | No row icons (`H:579` rowHref) and no row context menu in any `UI/data-grid*` file |
| Detail header like OI | `DESIGN-LANGUAGE.md:203` (one CTA in PageHeader) | `RecordHeaderCard` + `DetailActions` (`OID:771-990`) |
| CRM forms = portal forms | Not found | Price tag create renders the portal form (`PriceTagRequestPage.tsx:7,16,23-34`) |
| No invented rules / plain states | `NEVER-STUCK-UI.md:1,8` (bounded honest final state) | See section 3, "Empty, error, no-access" |
| One image pipeline | Not found | One shared `AttachmentDropzone` on the portal form (`AttachmentDropzone.tsx:271,318,392`) |

## 3. Summary table: playbook rule -> status -> evidence

Statuses: **Conforms**, **Partial**, **Missing**, **CRM better** (proposal back to Kay, section 7),
**Conflict** (an owner rule wins; section 6), **Not checked**.

Path keys: `FE` = `sorento_crm_frontend/`; `UI` = `FE/components/ui/`; `C` = `FE/components/common/`;
`H` = `FE/app/(protected)/project-sales/order-inquiries/components/OrderInquiryHeadersList.tsx`;
`OID` = `FE/app/(protected)/project-sales/order-inquiries/[id]/components/OrderInquiryDetail.tsx`;
`RCD` = same folder, `ReserveConfirmDialog.tsx`;
`QFC` = `FE/app/(protected)/project-sales/[projectId]/quotation-documents/components/QuotationFormClient.tsx`;
`QDC` = `FE/app/(protected)/project-sales/[projectId]/quotation-documents/[documentId]/components/QuotationDocumentClient.tsx`;
`QLG` = `FE/app/(protected)/project-sales/[projectId]/components/QuotationLinesGrid.tsx`;
`PF` = `FE/app/(auth)/portal/components/PriceTagRequestForm.tsx`;
`PTD` = `FE/app/(protected)/dealer-kit/price-tag-requests/components/PriceTagRequestDetail.tsx`.

### Actions

| Playbook rule | Status | Evidence |
| --- | --- | --- |
| One Main Action per page, top right (`PB:83-88`) | Partial | Rule exists (`DESIGN-LANGUAGE.md:203`). Price tag detail: one (`PTD:894-908`); quotation form: one (`QFC:948`). OI detail shows **two filled buttons at once**, Confirm and Reserve (`OID:960-983`) |
| Main Action in Foundryx red `#CC3333` (`PB:83`, `PB:498`) | Conflict (brand) | `--primary: var(--color-blue-500)` light, `blue-600` dark (`FE/css/config.reui.css:11,133`) |
| Red action motion: light, magnet lean, arrow (`PB:89-92`) | Conflict (minimal UI) | None in code |
| Blocked action: reason under it + pulse (`PB:93-102`) | Missing | Quotation Save/Submit/Approve/Issue disable with no reason (`QFC:948-962`, `QDC:578-617`); one title-only tooltip (`QuotationVersionEditor.tsx:731-736`) |
| Confirm dialog words: question title, "what happens" line, never "Are you sure?" (`PB:105`) | Partial | `RCD:226-228` title "Reserve 3 lines on OI-..." (verb + object, not a question); `C/confirm-dismiss-dialog.tsx:25-37` "Discard changes?" then "Are you sure you want to close this dialog?"; "Are you sure" in 29 non-test files (e.g. `FE/app/(protected)/forms-management/forms/actions.tsx:64`) |
| Safe button named for what it keeps, action = verb + object (`PB:106`) | Partial | Action named well: "Reserve and send to {name}" (`RCD:287-293`), "Discard changes" (`confirm-dismiss-dialog.tsx`); safe button is a bare "Cancel" in both (`RCD:284-286`) |
| Press and hold 3 s to confirm (`PB:107-111`, `draft:1447-1448`) | Conflict (owner decision) | No hold anywhere. Destructive actions use the server-deferred countdown instead (`PRINCIPLES.md:255-262`, `C/DeferredActionButton.tsx:45-140`) |
| Several actions -> one Main + Other Action icon buttons (`PB:114-117`) | Conflict | Secondary actions live in a gear menu (`C/DetailActions.tsx:60-87`, `C/DetailActionsMenu.tsx:121-122`, `OID:819-957`, `PTD:845-890`) |
| Icon button labels are styled tooltips (`PB:135-139`) | Partial | aria-label yes (`PR-CHECKLIST.md:54`); gear uses native `title` (`C/DetailActionsMenu.tsx:121-122`); prev/next have no tooltip (`C/RecordNavigation.tsx:77,99`); about 57 `<Tooltip` vs hundreds of `title=` |
| Row icon buttons slide (`PB:141`) | Conflict | No row icons by design: row click opens (`H:579`, `ADR-PRODUCT-STANDARDS.md:84-91`) |
| Text buttons lift 2px on hover (`PB:142-143`) | Conflict (minimal UI) | 0 `hover:translate-y` in the frontend |

### When something is done

| Playbook rule | Status | Evidence |
| --- | --- | --- |
| Say what happened, never "Success!" (`PB:148`) | Partial | Good: "Switched to {name}" (`FE/app/providers/CompanyProvider.tsx:127`), "Cancelled. Nothing was applied." (`FE/hooks/useDeferredAction.tsx:145`). Generic: "{noun} saved" (`FE/app/(protected)/project-sales/_shared/hooks/useQuotationDocuments.ts:218`) |
| Toast with Undo, 6 s, time bar, pauses on hover (`PB:153`) | Partial / CRM better | Sonner via `FE/lib/toast.ts:35-45` (success 4 s, error 5 s, no Undo); undo is done before commit by the deferred countdown toast with Cancel (`FE/hooks/useDeferredAction.tsx:145-190`) |
| Done page / done state for sends (`PB:154`) | Partial | Reserve dialog turns into a result table with Close (`RCD:169,266-270`); quotation save navigates away (`QFC:902-962`) |

### Lists

| Playbook rule | Status | Evidence |
| --- | --- | --- |
| Labels once, in a header row (`PB:175`) | Conforms | DataGrid header row |
| Smart view with info lines under rows (`PB:177`) | Conflict (one line per row) | `H:344,359,374,407` truncate + title |
| Table view with a sideways slider (`PB:178`) | Conforms | It is the only view: `UI/data-grid-table.tsx:1016,1300` |
| Phones: stacked cards (`PB:179`) | Conflict | No card layout; the table scrolls inside its box (`UI/data-grid-table.tsx:165,1251`) |
| Frozen header row (`PB:180`) | Conforms | Sticky by default (`UI/data-grid.tsx:187,333`, `UI/data-grid-table.tsx:1281-1300`) |
| Columns panel: show/hide/order, remembered (`PB:181`) | CRM better | `UI/data-grid-list-toolbar.tsx:185,293`; saved server-side per user and listing key (`UI/data-grid.tsx:163-166,420`, `documentation/reference/LISTING-COLUMN-PREFERENCES.md`), so it follows the user across devices |
| Drag to reorder columns (`PB:182-191`) | Partial | `moveColumn` in the header menu (`UI/data-grid-column-header.tsx:260-267`) and `UI/data-grid-table-dnd.tsx`; lift/glide detail Not checked |
| Header search, filter and sort by column type (`PB:192-202`) | Missing | Header click sorts only; a `filter` slot exists but OI passes none (`UI/data-grid-column-header.tsx:38,200`, `H:335-516`); filters live in a panel (`H:620-741`) |
| Long lists in pages, server-side, page in the address (`PB:203-209`) | Partial | Pager with numbers and ellipsis (`UI/data-grid-pagination.tsx:93-150`), "{from} - {to} of {count}" (`:53`), page/limit/sort in the URL (`H:141,150-161`); default 25 rows, playbook says 50 (`UI/data-grid-pagination.tsx:41`, `H:141`) |
| Empty: nothing yet (`PB:211`) | Conforms | "No order inquiries yet" (`H:561-567`); the one way to make one is the header CTA (`DESIGN-LANGUAGE.md:203`) |
| Empty: nothing matches + Clear filters in the state (`PB:212`) | Conflict (minor) | "No order inquiry matches this search and filter." (`H:561-567`); owner rule: an empty state is never a button (`DESIGN-LANGUAGE.md:203-205`); Clear filters sits in the toolbar (`H:731-741`) |
| Couldn't load: plain words + Try again (`PB:213`) | Conforms | `C/ListLoadFailure.tsx:23` with Retry |
| No access: who can open it + way back (`PB:214`) | Missing | No shared 403 state; ad hoc "Forbidden - you don't have permission..." (`FE/app/(protected)/system-management/ai-assistant/usage/page.tsx:141`, `.../numbering-rules/components/NumberingRulesList.tsx:123`) |
| Hold to Copy (`PB:218-225`) | Conflict (minimal UI) | No shared copy helper; ad hoc `navigator.clipboard` (`.../chat-history/components/TurnPanel.tsx:309`) |
| Select all with mixed state (`PB:226-228`) | Conforms / CRM better | Indeterminate header box (`UI/data-grid-select-column.tsx:53,62`); plus Odoo-style ranges (`UI/data-grid-range-select.ts:8-21`) |
| Selection bar: count, actions, clear (`PB:229-235`) | Conforms | "N selected", bulk "Send to purchasing", Clear (`UI/data-grid-list-toolbar.tsx:39-40,220`, `H:614-640`); a bulk delete is ONE deferred action naming the count (`PRINCIPLES.md:262`) |
| Text filter + column filters + "Showing n of N" (`PB:237`) | Partial | Search box + filter panel + Clear filters (`H:620-741`); count only in the pager |
| One top-bar search across everything (`PB:238`) | Conforms | Cmd/Ctrl+K dialog (`FE/app/components/partials/dialogs/search/search-dialog.tsx:61,115`); record scope Not checked |

### Fields

| Playbook rule | Status | Evidence |
| --- | --- | --- |
| Field hover lift (`PB:244`) | Conflict (minimal UI) | None |
| Dropdowns: never the browser's own (`PB:245`) | Conforms | SearchableSelect everywhere (`ADR-PRODUCT-STANDARDS.md:43`, `CLAUDE.md` CRUD UX) |
| Searchable: fetched with a pause, + Create (`PB:246-251`) | Conforms | Async with 200 ms debounce (`FE/hooks/useDebouncedSearch.ts:6`); `createOption` (`C/SearchableSelect.tsx:167,379,546`) |
| Date fields: typed or picked (`PB:252-258`) | Partial | Shared picker types DD/MM/YYYY (`UI/date-picker.tsx:29,65,133`, `UI/date-range-picker.tsx:28`); price tag Need by uses a native `<Input type="date">` (`PF:2400-2406`) |
| Date display "14 Nov 2026" (`PB:253`, `draft:1337`) | Conflict (dd/mm/yyyy) | `FE/lib/helpers.ts:128` dd/MM/yyyy, `:446-460` en-GB 2-digit |
| Calendar days never shift with time zone (`PB:257`) | Conforms | YYYY-MM-DD on the wire (`ADR-PRODUCT-STANDARDS.md:71-80`) |
| No browser number arrows; wheel never changes a value (`PB:260`) | Conforms | Qty is a text input with `inputMode="decimal"` (`QLG:709-717`) |
| Steppers for small counts (`PB:261-263`) | Missing | No minus/plus stepper anywhere on the quotation |
| Money fields: RM inside, right-aligned, tabular, tidy on blur, decimal keypad (`PB:279-283`) | Partial | Right-aligned tabular `inputMode="decimal"` (`QLG:713-717`); "RM" in the column heading ("Rate (RM)", `QLG:799-804`), which is the playbook's own Documents rule (`PB:483`); tidy on blur Not checked |
| Long single-line text scrolls sideways (`PB:284-288`) | Partial | Description is rich text and wraps (`QLG:624-630`); labels truncate with title (`QLG:453,648`) |
| Every scrollbar slim and styled (`PB:287`) | Missing | Only opt-in `.kt-scrollable-*` (`FE/css/components/scrollable.css:5-30`) |
| Adjustable text column (`PB:289-292`) | CRM better | Resizable, widths/order/visibility saved per user (`QLG:2051,2131,1348`) |
| Rich text: slim toolbar of allowed formats, paste keeps only those, live preview (`PB:294-299`) | Partial | TipTap with the 'full' toolbar incl. colour (`UI/rich-text-editor.tsx:8-18,198,285,338`); cover preview exists (`QuotationLetterPanels.tsx:62,120,132`); paste filtering Not checked |
| Adding files: drop zone, per-file rows, progress, retry, paste (`PB:300-305`) | Partial | Drop + paste (`FE/app/(auth)/portal/components/AttachmentDropzone.tsx:271,318,392`); failure is one toast "Upload failed." (`:238`), no per-file retry |
| Form errors next to the field (`PB:312`) | Partial / CRM better | Inline + scroll to the first error + auto-open its section (`PF:218,1111,2243,2408`); quotation line errors are title-only (`QLG:711-715`); detail actions toast only (`PTD:274-389`) |

### Toggles, navigation, panels

| Playbook rule | Status | Evidence |
| --- | --- | --- |
| Tabs are segmented toggles with a sliding thumb (`PB:317-324`) | Conflict (repo rule) | Tab strips are line tabs; only a two/three-option switch is segmented (`PR-CHECKLIST.md:52-53`); `TabsList variant="line"` with no sliding indicator (`OID:999-1023`, `UI/tabs.tsx:103-131`) |
| Side panel: auto rail, hover open, pin, timed slide (`PB:343-347`) | Partial | Icon rail + hover open on fine pointers (`FE/css/demos/demo1.css:89-118`); manual persisted toggle (`FE/app/components/layouts/demo1/layout.tsx:21,42`); no auto-hide timing |
| Floating AI widget only when locked (`PB:380-393`) | Conflict | The AI assistant bubble is always floating (`FE/app/components/common/AIAssistantBubble.tsx:595`) |
| Quick Tool widget, Clipboard panel, screenshot editor (`PB:394-427`) | Conflict (minimal UI) | None |
| RCT: hold the right button for a tool list (`PB:413-420`) | Conflict (right-click = row menu) | Right-click is reserved for record menus (owner rule) |
| Hover tooltips styled like the copy tip (`PB:428`) | Missing | Solid `bg-zinc-950` tooltip (`UI/tooltip.tsx:46`); mostly native `title` |
| Panels ease out (`PB:429`) | Conforms | Spring presets (`FE/lib/motion.ts:1-25`, `UI/dialog.tsx:144-169`, `UI/alert-dialog.tsx:77-105`) |
| Phone top bar condenses, red action floats (`PB:430-438`) | Missing | Header fixed, only its border changes (`FE/app/components/layouts/demo1/components/header.tsx:50,62-65`); no floating CTA |
| System banners take their own height (`PB:439-445`) | Conforms (partial) | Impersonation banner offsets the header (`FE/components/impersonation/ImpersonationBanner.tsx`, `header.tsx:62`); no maintenance or offline banner |
| Previews in a lightbox (`PB:457-464`) | Conforms | Price tag live preview (`PF:2362-2380`), `DesignLightbox` (`RequestDesignSection.tsx:20`) |
| Charts (`PB:466-476`) | Not checked | Two libraries in use, recharts and apexcharts (`FE/package.json`) |
| Documents / PDFs (`PB:478-487`) | Not checked | Out of this lane's six screens |

### Theme, responsive, motion

| Playbook rule | Status | Evidence |
| --- | --- | --- |
| Theme panel: 3 palettes per mode, font picker, size slider (`PB:491-497`) | Missing | Light/dark/system only (`FE/providers/theme-provider.tsx:8-14`, `FE/app/components/partials/topbar/user-dropdown-menu.tsx:56-63`) |
| Tokens only, written in OKLCH (`PB:499-531`) | Partial | Tokens alias the Tailwind 4 palette (`FE/css/config.reui.css:3-11`), which Tailwind 4 defines in OKLCH; but 713 raw palette classes and 12 raw hex in components (e.g. `UI/rich-text-editor.tsx:724`, `UI/tooltip.tsx:46`) |
| One font token (`PB:533-541`) | Conforms | `--font-sans: var(--font-inter)` (`FE/css/config.reui.css:253`, `FE/app/layout.tsx:2`); Inter is on the playbook's list, Geist is its default |
| Headings balanced (`PB:542`) | Missing | No `text-wrap: balance` in `FE/css` or `UI` |
| See-through floating surfaces, 50% + 6px blur (`PB:543`) | Partial / CRM better | Dialog scrim `bg-black/50 backdrop-blur-md` with a reduced-transparency fallback (`UI/primitive-classes.ts:36-39`); page header not translucent |
| Foundryx UIUX master switch + Advanced settings (`PB:545-584`) | Missing | Expected: comes with step 7, after the owner confirms |
| 360px to desktop, no page scroll sideways (`PB:588`) | Conforms | Mandate at 375 and 1280 (`PRINCIPLES.md:229,290`) |
| Phone header: actions stay together at the right (`PB:590`) | Conforms | `C/RecordHeaderCard.tsx:47` stacks, `C/DetailActions.tsx:66-87` wraps under the identity |
| Motion smooth, shared presets (`PB:599-610`) | Conforms | `FE/lib/motion.ts:1-25`, `DESIGN-LANGUAGE.md:47-64` |
| Pop on hover for every clickable item (`PB:611-624`) | Conflict (minimal UI) | None |
| Reduced motion (`PB:631-634`) | Conforms | `FE/css/styles.css:80-132,178` |
| Loading shows the shape (`PB:635-641`) | Partial | Row skeletons (`UI/data-grid-table.tsx:396-449`), route skeleton (`.../order-inquiries/loading.tsx:1-5`); pulse, not shimmer (`UI/skeleton.tsx:27`); no per-value "Calculating" on quotation totals (`QLG:861-867`) |
| Over 10 s say what is happening (`PB:640`) | CRM better | Every screen reaches an honest final state in bounded time (`NEVER-STUCK-UI.md:1,8`) |

## 4. Checklist on six real screens

The playbook Checklist (`PB:643-658`), per screen. Items that need the Foundryx UIUX switch or
`ui-audit.cjs` are left out (both come later, at step 7).

**OI list (`H`, route `FE/app/(protected)/project-sales/order-inquiries/page.tsx`)**
- One Main Action: Conforms (header CTA only; no row icons, `H:579`).
- Labels once, Select all, filter: Conforms (`UI/data-grid-select-column.tsx:53,62`, `H:620-741`).
- Smart view / Table view, per-view Columns: Conflict (one view, one line per row, `H:344-407`).
- Header search/filter by type: Missing (`UI/data-grid-column-header.tsx:38,200` unused).
- Frozen header row: Conforms (`UI/data-grid.tsx:187,333`).
- Phones show cards: Conflict (sideways scroll, `UI/data-grid-table.tsx:1016`).
- Hold to Copy + Clipboard: Conflict (minimal UI).
- Owner-rule gaps found on the way: Reserve not sortable (`H:491`); Reserve filter single-select (`H:665`).

**OI detail header (`OID`)**
- At most one Main Action: **Fails** - Confirm and Reserve can both be filled at once (`OID:960-983`).
- Other Actions as icon buttons with tooltips: Conflict (gear menu, `C/DetailActions.tsx:60-87`); gear tooltip is native `title` (`C/DetailActionsMenu.tsx:121-122`), prev/next have none (`C/RecordNavigation.tsx:77,99`).
- Never repeats further down: Conforms (no bottom bar; Lines tab's Reserve as requested / Reject is a different action, `OID:1049-1057`).
- Status as Badge: Conforms (`OID:771-810`).
- Dates: dd/mm/yyyy + 12h time (`OID:808`, `FE/lib/helpers.ts:446-460`).
- Empty related tabs: text only, no heading + hint split (`FE/app/(protected)/project-sales/order-inquiries/[id]/components/OrderInquiryRelatedDocumentsTab.tsx:242,293,321`).

**Quotation editor, money form (`QFC`, `QLG`)**
- One Main Action: Conforms ("Save quotation", `QFC:948`; the others are outline).
- No number arrows; counts use a stepper: arrows Conform (`QLG:709-717`), stepper Missing.
- Money uses the RM field: Partial (RM in the column heading, `QLG:799-804`).
- Blocked action has its reason under it: Missing (`QFC:948-962`, `QDC:578-617`).
- Done states: Partial ("{noun} saved" toast, no Undo, `useQuotationDocuments.ts:218`; autosave indicator "Saving.../Saved 2:14 PM/Save failed + Retry", `QFC:828`).

**Confirm dialog (`RCD`, Reserve and send)**
- Title as a question with its object: Partial ("Reserve 3 lines on OI-...", a statement, `RCD:226-228`).
- Safe button named for what it keeps: Missing (bare "Cancel", `RCD:284-286`).
- Action verb + object: Conforms ("Reserve and send to {name}", `RCD:287-293`).
- Page red action hides while open: Conforms (modal dialog over the page).
- 3 s hold: Conflict (owner decision; section 6, Q5).
- Done state names the result: Conforms (result table, `RCD:169,266-270`).

**Price tag request (`PF` for create, `PTD` for detail)**
- One Main Action: Conforms (`PTD:894-908`, gear menu `PTD:845-890`).
- Status pill via Badge: **Fails** repo rule `PR-CHECKLIST.md:42` (custom span, `PTD:137,785-788`).
- Date field typed or picked, dd/mm/yyyy: **Fails** (native `type="date"`, `PF:2400-2406`; the browser draws it in its own locale).
- Errors next to the field: Conforms and better (`PF:218,1111,2243,2408`).
- Adding files: Partial (drop + paste; no per-file retry, `AttachmentDropzone.tsx:238`).
- Preview: Conforms, lightbox (`PF:2362-2380`, `RequestDesignSection.tsx:20`); one Sheet for version history (`RequestDesignSection.tsx:23,232`) against the owner's dialog-over-side-panel rule.
- CRM form = portal form: Conforms for create (`PriceTagRequestPage.tsx:7,16,23-34`); the marketing detail is its own component.

**Phone layout (375 px)**
- No page-level sideways scroll: Conforms by mandate (`PRINCIPLES.md:290`); not re-measured in a browser in this lane.
- Header actions together at the right: Conforms (`C/RecordHeaderCard.tsx:47`, `C/DetailActions.tsx:66-87`).
- Lists as cards: Conflict (table scrolls inside its box).
- Top bar condenses, red action floats: Missing (`header.tsx:50,62-65`).
- The only floating element is the AI bubble (`AIAssistantBubble.tsx:595`).

## 5. Top 10 quick wins that fit the owner rules

Each is a small, self-contained change; none adds a floating widget, a hover effect or a new rule.

1. **OI detail: one filled CTA at a time.** When both show, keep the one the state is waiting for filled and make the other outline or move it to the gear menu (`OID:960-983`; rule `DESIGN-LANGUAGE.md:203`).
2. **OI list: Reserve filter multi-select** (`H:665`, owner: all dropdown filters multi-select). Same pass: make Reserve sortable server-side (`H:491`), which may need a backend sort key (UNVERIFIED).
3. **Price tag Need by: shared `DatePicker`** instead of native `type="date"` (`PF:2400-2406`), so it types and shows dd/mm/yyyy like every other date (`UI/date-picker.tsx:65`).
4. **Price tag status: `<Badge status>`** instead of the custom span (`PTD:137,785-788`; `PR-CHECKLIST.md:42`).
5. **Blocked primary says why, under it, in plain words** (no pulse): quotation Save/Submit/Approve/Issue (`QFC:948-962`, `QDC:578-617`).
6. **Confirm dialog words:** drop "Are you sure..." (29 files); the line under the title says what happens. Start with the shared `C/confirm-dismiss-dialog.tsx:25-37` (one file, every importer) and name its safe button for what it keeps ("Keep editing" instead of "Cancel"); same for `RCD:284-286`.
7. **One shared no-access state:** who can open it and a way back, replacing ad hoc "Forbidden - ..." text (`.../ai-assistant/usage/page.tsx:141`, `.../NumberingRulesList.tsx:123`).
8. **Upload failure per file, with Try again** in the one shared `AttachmentDropzone` (`:238`), so one fix covers every upload screen (owner: one image pipeline).
9. **Header icon buttons get the shared Tooltip:** gear (`C/DetailActionsMenu.tsx:121-122`) and prev/next (`C/RecordNavigation.tsx:77,99`); two shared files cover every detail page.
10. **Write the owner rules into the repo's own contract:** dd/mm/yyyy via one formatter, one line per row, all columns sortable server-side, all dropdown filters multi-select, right-click row menus, dialog over side panel, one image pipeline. Today none is in `DESIGN-LANGUAGE.md` (section 2), so reviewers cannot enforce them. Docs only.

Next after these (larger, not quick): consolidate the six date helpers behind one (`FE/lib/helpers.ts`);
global slim scrollbars and balanced headings (one CSS file each, but they touch every page's look,
so they ride the switch at step 7); the right-click row menu the owner already asked for (not built in
any `UI/data-grid*` file).

## 6. Agreed-difference candidates (conflicts)

Each needs the owner's answer before `playbook-uiux.md` is written. Filed as one `crew report --ask` (Q1-Q5).

| # | Playbook | CRM / owner rule | Recommendation |
| --- | --- | --- | --- |
| Q1 | Dates read "14 Nov 2026" (`PB:253`, `draft:1337`) | dd/mm/yyyy via one shared formatter (`FE/lib/helpers.ts:128,446`) | **Keep ours.** The shared helpers already output dd/mm/yyyy; the owner rule names it |
| Q2 | Smart view with info lines; cards on phones (`PB:176-179`) | Standard DataGrid, one line per row; phones scroll inside the box (`H:344-407`, `UI/data-grid-table.tsx:1016`) | **Keep ours.** Adopt only what fits one line: header filter by column type later (`PB:192-202`) |
| Q3 | Other Actions as header icon buttons; row icon buttons; RCT on the right button (`PB:114-141`, `PB:413-420`) | Gear menu in the header (`C/DetailActions.tsx:60-87`); right-click row menu (owner) | **Keep ours.** RCT takes over the right button the owner reserved for row menus |
| Q4 | Minimal-UI clashes: Foundryx red CTA with lean and light; hover pop on everything; Hold to Copy, Clipboard, Quick Tool, floating AI only when locked (`PB:83-92`, `PB:218-225`, `PB:394-427`, `PB:611-624`) | Sorento blue `--primary` (`FE/css/config.reui.css:11`), no hover lift, AI bubble always shown (`AIAssistantBubble.tsx:595`) | **Keep ours.** Brand colour and minimal UI; adopt only the styled tooltip (`PB:428`) since it replaces, not adds |
| Q5 | 3 s press-and-hold confirm dialog (`PB:103-113`) | Delete/Archive/Unlink: server-deferred countdown, no dialog (`PRINCIPLES.md:255-262`); other irreversible sends keep a click-confirm dialog (`RCD`) | **Keep the countdown; no hold** (a hold is new behaviour). **Adopt the playbook's dialog words** for the remaining dialogs (quick win 6) |

Smaller differences, recorded but not asked (the repo rule already decides them): line tabs, not
segmented toggles (`PR-CHECKLIST.md:52-53`, `UI/tabs.tsx:103-131`); "Nothing matches" has no Clear filters
button inside the state (`DESIGN-LANGUAGE.md:203-205`); 25 rows per page by default, not 50
(`UI/data-grid-pagination.tsx:41`).

## 7. Rules the CRM does better (proposals back to Kay, report only)

Report only; nothing is sent to `foundryxkay/playbook-UIUX` from this lane.

1. **Deferred destructive action** (`PRINCIPLES.md:255-262`, `C/DeferredActionButton.tsx:45-140`, `FE/hooks/useDeferredAction.tsx`): the button becomes a countdown with Cancel, the server commits when it lapses even if the tab closes, a batch is one action naming its count. No dialog, nothing to misclick, and undo needs no reverse operation. Proposed for "Confirm before what can't be undone" as the delete pattern.
2. **Range selection like Odoo/Gmail** (`UI/data-grid-range-select.ts:8-21`): Shift+click, drag across tick boxes, Shift+Arrow, and a 500 ms hold before a touch drag so a finger still scrolls. Proposed under "Selecting".
3. **Columns saved per user on the server** (`UI/data-grid.tsx:163-166`, `documentation/reference/LISTING-COLUMN-PREFERENCES.md`), not per browser: the same columns on every device. Proposed under "Columns".
4. **Never stuck** (`documentation/reference/NEVER-STUCK-UI.md:1,8`): every screen reaches an honest final state within a bounded time. Broader than "Over 10 s" (`PB:640`); proposed under Loading.
5. **Errors you can find** (`PF:218,1111`): submit scrolls to the first error and opens the collapsed section that holds it. Proposed under "Form errors".
6. **Reduced transparency** (`UI/primitive-classes.ts:36-39`): see-through surfaces fall back to an opaque scrim with no blur when the OS asks for it. Proposed under "See-through surfaces".
7. **Autosave with a visible state** (`QFC:828`, `FE/app/(protected)/project-sales/[projectId]/quotation-documents/components/useQuotationFormAutosave.ts:17`): "Saving... / Saved 2:14 PM / Save failed + Retry". The playbook has no autosave rule. Proposed as a new Fields rule.

## 8. Not covered by this audit

`scripts/ui-audit.cjs` (no adapter), Documents/PDF layout, Charts, Wizards, the full 469-page sweep,
light/dark visual check, and a live 375 px browser pass. All screen claims are from code with
`file:line`; anything marked UNVERIFIED or Not checked was not confirmed.
