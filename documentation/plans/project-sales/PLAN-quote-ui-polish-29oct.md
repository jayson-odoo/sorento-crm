# PLAN: quotation series default, product picker code only, projects list no underline (QUOTE-UI-POLISH)

Status: Build. Small fix track (3 frontend tweaks, no migration, no auth/RBAC, no new ingest; expected diff well
under 300 lines). UAC: `quote-ui-polish-29oct-acceptance-criteria.md` (same folder).

Owner, 29 Oct ~10:00 (verbatim): "for the series, if it is only 1 option then we should default, why in quotation,
got this two column one, just show product code only, otherwise will look truncated, i don't want this underline,
it is not aligned with our system design language"

## 1. Series: one option = the default

Where: `app/(protected)/project-sales/[projectId]/components/QuotationDialog.tsx:119` (the Edit / Add scope dialog,
used by the quotation form page and the project page) and the quotation form page's own new scopes
(`quotation-documents/components/QuotationFormClient.tsx:101` `newScope()`, called at :232 for the first scope and
:547 for "Add a scope", which asks for a name only).

Rule: when exactly ONE active series exists (`useProjectSeries()`, filtered `is_active`), a scope with no series
starts with that one.

- Dialog: preselect once, when the series list arrives, only if the scope has none. Clearing it afterwards sticks
  (still `clearable`: "no series" stays a legitimate answer, the dialog's own doc comment).
- Form page: every NEW scope (no id) with no series is given the sole series once, so the lines tab judges
  non-standard lines against it (`QuotationVersionEditor` `seriesId`) and Save writes it. Saved scopes that have no
  series are not rewritten silently; opening their Edit dialog preselects it.
- `isUntouchedNewScope` (:115) drops its `!scope.series_id` term: a defaulted series must not make the blank first
  scope "touched". The term was redundant already: the only other way to set a series is the dialog, whose submit
  also writes a non-empty name (`scopeTitle` fallback, submit disabled on a blank name).
- Zero or two+ series: unchanged ("No series" placeholder).

## 2. Product picker: code only

Where: `app/(protected)/project-sales/[projectId]/components/QuotationLinesGrid.tsx:279` `renderLineOption`, local
to the quotation lines grid (no other importer). It renders `label` (product code) and `description`
(`product_name`, which in Sorento IS the code) side by side, so the code shows twice and the grey copy truncates.

Fix: every option renders its label alone, one line that wraps (`break-words`), no truncation. Shared
`components/common/SearchableSelect` is untouched, so no other screen changes.

## 3. Projects list: no underline

Where: `app/(protected)/project-sales/_shared/components/ProjectsGrid.tsx:104` (Code) and `:122` (Project title),
both `hover:underline`. Only importer: `pipeline/components/PipelineClient.tsx:446` (Pipeline > Grid), which passes
`rowHref` so the whole row is the link.

House style: Orders list primary column is plain text with row navigation from `rowHref`
(`order-management/orders/components/OrdersList.tsx:183`, `:352`); Sample Requests, same module, a plain
`truncate font-medium` span (`sample-requests/components/SampleRequestsList.tsx:126`).

Fix: drop `hover:underline` from both cells. The `Link` stays (the title is still a link for keyboard and
open-in-new-tab, guarded by `ProjectsGrid.approval.test.tsx:181`).

Not changed, flagged: `leads/components/LeadsGrid.tsx:101,115` carries the same two `hover:underline` cells.

## Tests (red first)

- `QuotationDialog.test.tsx` (new): one active series -> preselected on a scope with none; kept when the scope has
  one; two series -> none preselected; clearing sticks.
- `QuotationFormClient.test.tsx`: one active series -> the first new scope saves with it; header-only save still
  leaves the untouched first scope out.
- `QuotationLinesGrid` picker: an option whose description equals its code renders the code once.
- `ProjectsGrid.v2.test.tsx`: the Code and Project cells carry no underline class.

## Verification

vitest on touched files, kill test, reviewer, agent-browser 1280/375 on the crew test copy, hand test.
