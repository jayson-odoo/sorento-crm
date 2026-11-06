# PLAN: purchasing email has exactly one trigger (board Confirm)

Status: Plan (behaviour card pending owner answers). Track: M, LEAD pattern.

## Owner ruling (6 Nov 2026)
"the rule of thumb is, I only want the email to purchasing to have 1 trigger, which is this button"
(Fulfilment Planning dialog, "Confirm N order(s)").

## Why
SO398322 (4 Nov): AutoCount sync re-keyed a line; SO ingest retired the OI row and auto-emailed
purchasing a false cancel. Re-key matching itself is lane AC-REKEY-SAME-LINE (not duplicated here).

## Steps
1. Behaviour card: every path that emails purchasing, recipient proven, KEEP/STOP.
2. One structural gate: the purchasing handover dispatch is reachable only from the Confirm path.
3. Red tests per path, kill test, reviewer.
