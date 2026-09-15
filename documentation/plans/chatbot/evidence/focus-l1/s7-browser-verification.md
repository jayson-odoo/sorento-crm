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

## S7c re-run at 98903432d

Branch `feat/chatbot-focus` at 98903432d (S7c built - the AND-mode `entity_pins`
narrowing fix). agent-browser session `focus-s7c`. Same stack (FE :3081, BE :8081),
contact Jayson, prompt version v15. Run: 2026-09-13.

### Summary

| Step | Result |
|---|---|
| Chain G re-run: 10-row picker, sequential picks 10/9/8, casual turn, then 4 (also a prefix code) | PASS |

### Chain G re-run - the prefix-code pin fix confirmed

| Step | Message | Reply (first line) | Result | Version |
|---|---|---|---|---|
| 1 | incoming wc286 | incoming search needs to be more specific. Multiple matches found. Please choose: | PASS (same 10-row roster: row 8 SRTWC286-SH-NEW-P, row 9 SRTWC286-SH-NEW-200, row 10 SRTWC286-SH-NEW) | v15 |
| 2 | 10 | I have attached the file(s) below. | PASS - see verbatim reply below | v15 |
| 3 | 9 | I have attached the file(s) below. | PASS (SRTWC286-SH-NEW-200 only) | v15 |
| 4 | 8 | I have attached the file(s) below. | PASS (SRTWC286-SH-NEW-P only) | v15 |
| 5 | thanks | You're welcome! Happy to help. | PASS (casual, low_signal) | v15 |
| 6 | 4 | No incoming stock (ETA) found for SRTWC286-SH. | PASS (SRTWC286-SH only) - see note below | v15 |

Step 2 reply, copied verbatim (the exact defect from the prior S7 run - "10" answered with
SRTWC286-SH-NEW-200 instead of its own code - is fixed):

```
10

I have attached the file(s) below.

1. *Product Code:* SRTWC286-SH-NEW
*Container:* WHSU7382874
*Loading:* 2026-08-28
*ETC:* 2026-08-29
*ETD:* 2026-08-31
*ETA:* 2026-09-08
*ETA Delay:* 2026-09-08
*Liner:* WHL
*China Forwarder:* J&H
*Malaysia Forwarder:* MPM
*Consignee:* Sorento
*Free Days Available:* 14
*Incoming Quantity:* 209
(PENDING ALLOCATION)

2. *Product Code:* SRTWC286-SH-NEW
*Container:* WHSU7390118
*Loading:* 2026-08-28
*ETC:* 2026-08-29
*ETD:* 2026-08-31
*ETA:* 2026-09-08
*ETA Delay:* 2026-09-08
*Liner:* WHL
*China Forwarder:* J&H
*Malaysia Forwarder:* MPM
*Consignee:* Sorento
*Free Days Available:* 14
*Incoming Quantity:* 105
(PENDING ALLOCATION)
```

Checked programmatically (full-page text search): none of "SRTWC286-SH-NEW-150",
"SRTWC286-SH-NEW-P", "SRTWC286-SH-NEW-200" appear anywhere in this reply. Both rows name
only SRTWC286-SH-NEW, row 10's own code.

Note on step 6 ("4", also a prefix code - SRTWC286-SH is a prefix of -SH-150, -SH-200,
-SH-NEW, -SH-NEW-150, -SH-NEW-P, -SH-NEW-200, -SH-P, -SH-PP, -SH-UF): the primary
stock answer is correctly scoped to SRTWC286-SH only (four warehouse rows, all
`*Product Code:* SRTWC286-SH`, no sibling code in the data). The reply then APPENDS a
separate "Related products:" section re-listing all 10 family codes as a fresh follow-up
picker ("Reply with a number to check its incoming, or reply 'yes' to escalate to
purchasing team.") - a different, apparently intentional feature (a follow-up suggestion
list), not the picked-product answer being polluted with siblings. Recorded verbatim
since it does name every sibling code, even though it is not the same defect as the "10"
bug: the answer's OWN data stayed scoped to one product.

Screenshot: `s7c-g.png`.

No browser console errors or uncaught exceptions observed. Browser session `focus-s7c`
closed by name.
