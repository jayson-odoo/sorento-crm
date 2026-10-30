# UAC: Request CS to reserve - tick lines before sending (RESERVE-REQ-PICK)

Plan: `PLAN-reserve-request-pick-30oct.md`.

- AC-RP-1: Opening "Request CS to reserve" (OI page or Stock Debt snapshot drill) shows a tick box on
  every line and a tick-all box in the grid header; every line is ticked unless the caller pre-unticked it.
- AC-RP-2: The dialog header shows "N of M lines" and updates as lines are ticked or unticked.
- AC-RP-3: Send request / Park request posts only the ticked lines, each with its own Requested and
  Location.
- AC-RP-4: An unticked line's Requested and Location are disabled; an out-of-range Requested on an
  unticked line does not stop the send.
- AC-RP-5: With no line ticked, Send request / Park request is disabled.
- AC-RP-6: From the Stock Debt snapshot drill, a line whose snapshot row reads Short 0 (covered or
  pinned) opens unticked; lines still short open ticked. One constant switches this off.
- AC-RP-7: Usable and not clipped at 1280px and 375px.
