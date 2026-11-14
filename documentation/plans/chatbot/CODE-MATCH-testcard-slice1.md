# CHATBOT-CODE-MATCH slice 1: 10:00 test card (Chatbot Console, dry run, no WhatsApp send)

PR #2370, slice 1: dealer close-code offers, inactive codes never offered, every missed code gets its own offer,
`code_candidates` in the trace. Codes are catalogue codes from the 12 Nov review; pick a dealer contact
(availability-only) unless the line says staff.

| # | Contact | Type | Before (main) | After (this slice) |
| --- | --- | --- | --- | --- |
| 1 | dealer | `Swtwc8354-SH-UF x 3` | "Couldn't find SWTWC8354SHUF. Did you mean SRTWC8354-SH-UF?" (code shown without its dashes) or "Please refer to your salesman." | "Couldn't find SWTWC8354-SH-UF. Did you mean SRTWC8354-SH-UF?"; reply "yes" answers the stock of SRTWC8354-SH-UF for 3 units |
| 2 | dealer | `SRTWC8354-SH-UF x 2, Swtwc8152 x 1` | stock line, then "Couldn't find: SWTWC8152." with no offer | stock line, then "Couldn't find SWTWC8152. Did you mean ...?" with the close code(s) |
| 3 | dealer | `Swtwc8354-SH-UF x 1, Swtwc8152 x 2` | one list only (the second code gets nothing) | two "Couldn't find X. Did you mean:" lists numbered on; "1 and 2" answers both at x1 and x2; "no" refers to the salesman naming both codes |
| 4 | staff | a typo of a code that is INACTIVE in the catalogue (pick one from Products, status inactive) | the inactive code can be offered | the inactive code is never offered; an active sibling still is |
| 5 | dealer | an exact code, e.g. `SRTWC8354-SH-UF x 2` | answered | answered, unchanged |

After each turn, open the turn's trace in the Console: a missed code shows a `code_candidates` entry listing the
offered codes in order with their match tier and score.
