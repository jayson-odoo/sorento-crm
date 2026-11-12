# UAC: DATE-PICKER-UNIFY

Final (behaviour card answered 12 Nov).

- AC1 Typing `05/11/2026` into any migrated date field and leaving it stores `2026-11-05`; typing
  `5/11/2026` does too; `31/02/2026` stores nothing and the field keeps its last value.
- AC2 A stored `2026-11-05` reads `05/11/2026` in the field in every browser locale (en-US included).
- AC3 Picking a day in the calendar stores that same calendar day, whatever the browser timezone.
- AC4 Range field: typing `01/11/2026 - 30/11/2026` sets both ends; a single date sets from = to;
  `31/02/2026 - 01/03/2026` is refused and the text reverts.
- AC5 A request submitted at 2026-11-04 23:30 UTC (05/11/2026 07:30 Malaysia) shows Submitted date
  `05/11/2026`.
- AC6 An activity row created one minute ago (naive UTC timestamp) reads "1m ago", not "8h ago".
- AC7 SLA screens show UTC timestamps as Malaysia `dd/mm/yyyy, h:mm am/pm`.
- AC8 No native `type="date"` / `datetime-local` remains outside the guard's allowlist; the last
  slice leaves the allowlist empty.
- AC9 Payloads sent to the API are unchanged in shape (`YYYY-MM-DD` where it was).
- AC10 Range field: emptying the text and leaving clears both ends; `05/11/2026 -` sets From only;
  `- 30/11/2026` sets To only.
- AC11 A From/To date-time filter pair is one range field of whole days; From sends the start of the
  first day and To the end of the last day in the same two query params.
- AC12 A single date-time field is a date field plus a time box; the stored value is unchanged in shape.
