# UAC: OI-DATE-WAS-FIX

1. A row the oiod_0001 backfill moved, whose SO line has a pending `delayed` or `advanced`
   planning change, reads its pre-backfill delivery date again after the migration.
2. That row's change is recorded in `projects.oi_delivery_date_pending_restore`.
3. Rows without a pending delayed/advanced change are untouched; no email is sent by the migration.
4. CS Confirm of that change then sends the DELAY/ADVANCE email with Was and Now.
5. DROPPED (owner, 4 Nov ~18:00): the OI list-page Excel export and the per-project OI download end with a
   `WAS DELIVERY DATE` column: the previous date in dd/mm/yyyy when the row moved, blank otherwise.
