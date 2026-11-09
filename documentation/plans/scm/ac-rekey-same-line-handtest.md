# Hand test - AC-REKEY-SAME-LINE (PR #2219)

Repo copy of the `crew-handtest` posted on the PR, with crew's corrections from the 6 Nov pass on
7c7d9c3f (behaviour PASS). Setup script: `sorento_crm_backend/scripts/handtest_ac_rekey_setup.py`.

Three hand-test orders side by side: HT-REKEY-SAME (line re-keyed, the fix), HT-REKEY-REMOVED
(line really removed, today's behaviour), HT-REKEY-CHANGED (line re-created with a different qty,
today's behaviour). No email reaches anybody: the setup holds back the purchasing email that
REMOVED and CHANGED queue today and marks it cancelled.

## URL

crew test copy

## Setup

Crew only; the owner runs nothing.

1. Start the test copy on branch `claude/ac-rekey-same-line-utgkqw` (backend + frontend; the
   worker is not needed).
2. From `sorento_crm_backend/`, with the copy's env:
   `venv/bin/python scripts/handtest_ac_rekey_setup.py --apply`. If the copy's database name has no
   dev / ci / test / copy segment, add `--allow-db <that name>`. The script refuses any other
   database or a non-local host.
3. Keep the script's printout for the owner. It names the real SO it cloned (read only), the item,
   the qty Q of line Seq 10 and the three OI numbers, and must show `rekeyed': 1` on the
   HT-REKEY-SAME second push.
4. Held-back mail count. Where the "Order inquiry to purchasing" automation is enabled and a user
   holds a purchasing role, it reads `held back: 1` for REMOVED and CHANGED (0 for SAME). On the
   shared dev DB that automation is OFF, so all three read `held back: 0` and Outgoing Mails
   (step 15) shows nothing: tell the owner, the email check then rests on step 16 alone.
5. Log the owner in with a user whose PRIMARY role is superadmin (Planning history is
   superadmin only).
6. After the test: `venv/bin/python scripts/handtest_ac_rekey_setup.py --cleanup` (audit rows and
   any held-back mail rows stay).

## Steps

1. From `/`, open Project Sales Admin > Sales Orders.
2. Search `HT-REKEY-SAME` and open it.
3. Open the Lines tab.
4. Go back to Sales Orders, search `HT-REKEY-REMOVED`, open it, open the Lines tab.
5. Go back to Sales Orders, search `HT-REKEY-CHANGED`, open it, open the Lines tab.
6. Open Procurement > Supply Chain > Order Inquiries.
7. Click the Lines toggle.
8. Set the acknowledgement filter to All (the Lines view opens preset to Rejected).
9. Type `HT-REKEY` in the search box.
10. In the State filter, tick To buy AND Cancelled.
11. Hover the info icon in the Instruction column of each HT-REKEY row.
12. Open Supply Chain > Project Demand > Fulfilment Planning.
13. Search `HT-REKEY-SAME`, tick its row, click "Plan SO...".
14. Click the gear button (Board actions), then History.
15. Repeat steps 12 to 14 for `HT-REKEY-REMOVED`, then for `HT-REKEY-CHANGED`.
16. Open System > Messaging > Outgoing Mails and search `HT-REKEY`.
17. Open System > Messaging > Outgoing Mails > Email Outbox and search `HT-REKEY`.

## Expected

Q = the qty the setup printed for line Seq 10.

- Step 3, HT-REKEY-SAME:
  - exactly 2 lines, No. 10 and No. 20, both Status "Outstanding", no "Cancelled" line;
  - No. 10 shows Qty ordered Q;
  - No. 10's Order inquiry column shows the HT-REKEY-SAME OI number with "Done" (the row is
    acknowledged).
- Step 4, HT-REKEY-REMOVED:
  - exactly 2 lines;
  - No. 10 is Status "Cancelled", Qty ordered Q, with no "Done" in Order inquiry;
  - No. 20 is "Outstanding".
- Step 5, HT-REKEY-CHANGED:
  - exactly 3 lines;
  - one No. 10 is "Cancelled" with Qty ordered Q;
  - another No. 10 is "Outstanding" with Qty ordered Q - 1 and Order inquiry "-";
  - No. 20 is "Outstanding".
- Steps 9 to 11, Order Inquiries Lines (ack All, State To buy + Cancelled), exactly 3 HT-REKEY rows:
  - HT-REKEY-SAME's row reads "To buy", qty Q, and has no "Removed in AutoCount" note;
  - HT-REKEY-REMOVED's and HT-REKEY-CHANGED's rows read "Cancelled", and their info tooltip reads
    "Removed in AutoCount";
  - with Cancelled unticked, only the HT-REKEY-SAME row is listed.
- Step 14, HT-REKEY-SAME history: no "Order cancelled" entry and no "Email" entry.
- Step 15, HT-REKEY-REMOVED and HT-REKEY-CHANGED history: one "Order cancelled" entry each, no
  "Email" entry (the email is held back before the outbox).
- Step 16, Outgoing Mails:
  - with the automation enabled (Setup 4): exactly 2 HT-REKEY rows, subjects
    `OI: <location> @ HT-REKEY-REMOVED` and `OI: <location> @ HT-REKEY-CHANGED`, Status
    `cancelled`, Error "Hand-test setup: held back, never sent", Sent At empty, and no row
    mentions HT-REKEY-SAME;
  - on the shared dev DB (automation off): no HT-REKEY row.
- Step 17, Email Outbox: no HT-REKEY row at all.
