# S7 multiple-matches picker + dash fold - browser verification

Branch `feat/chatbot-focus` at 5aa1d9d65 (S7 built). Stack: FE http://localhost:3081, BE
http://localhost:8081. agent-browser session `focus-s7`. Contact "Jayson" (preselected).
Prompt version selector defaults to v13 on every load/reset (v16 is another lane's prompt on
this DB); v15 was selected before the run. Run: 2026-09-13.

## Summary

| Chain | Result |
|---|---|
| G. multiple-matches picker, sequential picks 8 / 10 / thanks / 9 | FAIL - see deviation below |
| H. topic_reset clarifier, one bubble, no dash | PASS |
| I. multiple-matches picker cleared by a new subject | PASS |

## Chain-by-chain transcript

### Chain G - `incoming wc286` multiple-matches picker

| Step | Message | Reply (first line) | Result | Version |
|---|---|---|---|---|
| 1 | incoming wc286 | incoming search needs to be more specific. Multiple matches found. Please choose: | PASS (10 numbered SRTWC286 rows, row 8 = SRTWC286-SH-NEW-P "has incoming") | v15 |
| 2 | 8 | I have attached the file(s) below. | PASS (Product Code SRTWC286-SH-NEW-P, an incoming answer, not "Could not find incoming") | v15 |
| 3 | 10 | (blank line) *Product Code:* SRTWC286-SH-NEW-200 | FAIL - see deviation below | v15 |
| 4 | thanks | You're welcome! Happy to help. | PASS (casual reply, roster still alive going into step 5) | v15 |
| 5 | 9 | I have attached the file(s) below. | PASS on its own (Product Code SRTWC286-SH-NEW-200, matches the expected code for this step) | v15 |

Deviation on step 3, recorded verbatim: the original picker's row 10 read "10. SRTWC286-SH-NEW
- has incoming". Answering "10" returned "*Product Code:* SRTWC286-SH-NEW-200" - row 9's code,
not row 10's own "SRTWC286-SH-NEW". Step 5's "9" then ALSO returned "SRTWC286-SH-NEW-200" (the
expected code for that step, per the chain script) - the SAME product two different positions
resolved to. Row 10's own product, SRTWC286-SH-NEW, was never reached by either "10" or "9" in
this run. This reads as an off-by-one on the tail end of the roster (positions 9 and 10 both
resolving to row 9's row), not a re-arm/consumption defect - screenshot `s7-g.png` (which
captures step 5's reply) and the request/reply text above are the record; filed here rather
than worked around.

Screenshots: `s7-g.png` (1280), `s7-g-375.png` (375).

### Chain H - `stock SRTWT2643`, topic_reset clarifier, one bubble

| Step | Message | Reply (first line) | Result | Version |
|---|---|---|---|---|
| 1 | stock SRTWT2643 | Couldn't find "SRTWT2643" (product). Did you mean: | PASS | v15 |
| 2 | 1 | Here's what you want: | PASS (SRTWT2632 + "escalate to purchasing team?") | v15 |
| 3 | another one | Do you mean you want another option from the list? | PASS | v15 |
| 4 | 2 | Could you share the options you're choosing from? | PASS (NOT a re-pick) | v15 |

Step 3 verbatim (the S7b fix, confirmed): exactly ONE reply bubble for "another one" - "Do you
mean you want another option from the list?" (`low_signal`). Checked programmatically
(`get text` over the whole page) for both U+2013 (en dash) and U+2014 (em dash): neither is
present anywhere in the transcript. This is the exact turn shape that produced TWO bubbles (one
folded, one with a raw em dash) in the S6 evidence run (chain E) - now one bubble, no dash,
confirmed both by text scan and by the screenshot showing a single reply card.

Screenshot: `s7-h.png`.

### Chain I - `incoming wc286` picker cleared by a new subject

| Step | Message | Reply (first line) | Result | Version |
|---|---|---|---|---|
| 1 | incoming wc286 | incoming search needs to be more specific. Multiple matches found. Please choose: | PASS (same 10-row roster as chain G) | v15 |
| 2 | SRTWC8517 stock? | Stock details found for the requested products. | PASS (new subject answered - SRTWC8517-SH-UF rows - roster cleared) | v15 |
| 3 | 8 | Stock details found for the requested products. | PASS (NOT a re-pick - answers about SRTWC8517 again, not row 8 of the old wc286 roster) | v15 |

Screenshot: `s7-i.png`.

## Console / network

No browser console errors or uncaught exceptions observed across the run.
