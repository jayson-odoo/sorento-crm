# UAC: PLAN-BATCH-COUNT-DISPLAY (21 Oct 2026)

Plan: `PLAN-batch-count-display-21oct.md`. Shape: SO394881, a pending AutoCount change from 24 Sep
retiring 10 old lines (SRTWCX8840-S-RL), 12 Cancel SO saved on replacement lines.

- D1. The board reads Confirm (12) and Saved (12): decisions only, never the 10 retired lines.
- D2. One plain note on the board: "Also applies the AutoCount change from 24 Sep: 10 old lines
  (SRTWCX8840-S-RL) are retired". With several SOs on the board, one line per SO, each prefixed
  with its SO number.
- D3. Simulate: "SO394881: would transfer 12 lines to Cancel SO", then "Would also apply the
  AutoCount change from 24 Sep: 10 old lines (SRTWCX8840-S-RL) would be retired".
- D4. Confirm: "1 of 1 orders confirmed", "SO394881: 12 lines transferred to Cancel SO", then
  "Also applied the AutoCount change from 24 Sep: 10 old lines (SRTWCX8840-S-RL) were retired".
- D5. An order whose only content is the pending change: Confirm (0) is still pressable and the note
  reads "Applies the AutoCount change from ..." (pending crew answer, option (a)).
