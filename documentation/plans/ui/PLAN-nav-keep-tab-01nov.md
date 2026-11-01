# PLAN: Record pager keeps the active tab (NAV-KEEP-TAB)

Status: built, in review, awaiting crew hand-test (small fix track: FE only, no migration, no auth/RBAC change)

## Journey
Owner ruling 1 Nov: on a detail page with a record pager ("7 / 73" with < >), pressing next or
prev keeps the reader on the tab they are on (e.g. Complaints > "Fulfilment DOs"). Unified for
every detail page.

## Design (shared layer, not page by page)
1. The active tab lives in the URL as `?tab=<key>`; the default tab writes no param.
2. `useListPager` (`hooks/useListPager.ts`) carries the current `tab` onto every step href
   (in-page step, cross-page step, prefetch). `parseDetailSearch` treats `tab` as reserved, so it
   is never mistaken for a list filter (no list-cache miss, no `tab=` sent to a list GET).
3. `useUrlTab` (`hooks/useUrlTab.ts`) is the one tab hook: `basePath` becomes optional (defaults
   to the current pathname), and a `?tab=` naming a tab this record does not render falls back to
   the default tab without rewriting the URL or erroring.
4. Every pager page whose tab state was `useState` / uncontrolled `defaultValue` moves to
   `useUrlTab`. Back/forward and a pasted URL then open the same tab for free.

## UAC
- A1 Next/prev (in-page and across a page boundary) keeps `?tab=`; list filters/sort kept.
- A2 Next record lacks the tab: default tab shown, no error.
- A3 Pasted URL / back / forward open the tab named in the URL.
- A4 Default tab carries no `tab` param; Back to list drops `tab` (already in `BackToList`).
- A5 Complaints detail: on "Fulfilment DOs", next lands on the next complaint's Fulfilment DOs.

## Tests (red first)
- `hooks/useListPager.keepTab.test.ts`: step hrefs carry tab; tab not a list filter.
- `hooks/useUrlTab.test.ts`: fallback, URL round-trip, optional basePath.
- Complaints page-level test: FormDetailWithSLATabs reads/writes `?tab=`.
