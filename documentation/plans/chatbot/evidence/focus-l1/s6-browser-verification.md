# S6 sticky roster (D19) - browser verification

Branch `feat/chatbot-focus` at 0a23fc304 (reds green, replay unmoved). Stack: FE
http://localhost:3081, BE http://localhost:8081. agent-browser session `focus-s6`. Contact
"Jayson" (preselected). Prompt version selector defaults to v13 on every load/reset; v15 was
selected before each chain. Run: 2026-09-13.

## Summary

| Chain | Result |
|---|---|
| A. did-you-mean roster, sequential picks 1/2/3 | PASS |
| B. promo tier menu, sequential picks 1/2/3 | PASS |
| C. roster survives a declined escalate offer | PASS |
| D. yes consumes the merged question (no re-pick) | PASS - see note on step 4's exact wording |
| E. topic_reset clears the roster | FAIL - see defects below |
| F. roster survives a casual turn | PASS |

## Chain-by-chain transcript

Each row: the message sent, the first line of the reply, PASS/FAIL, the prompt version shown
on the bubble.

### Chain A - `stock SRTWT2643` did-you-mean roster

| Step | Message | Reply (first line) | Result | Version |
|---|---|---|---|---|
| 1 | stock SRTWT2643 | Couldn't find "SRTWT2643" (product). Did you mean: | PASS | v15 |
| 2 | 1 | Here's what you want: | PASS (SRTWT2632 + "escalate to purchasing team?") | v15 |
| 3 | 2 | Here's what you want: | PASS (SRTWT2633, roster re-picked, not a re-answer of 2632) | v15 |
| 4 | 3 | But there is INCOMING stock (ETA) for the requested products: | PASS (SRTWT2634 variants) | v15 |

Screenshot: `s6-a.png`.

### Chain B - `promo for srtwc286` tier menu

| Step | Message | Reply (first line) | Result | Version |
|---|---|---|---|---|
| 1 | promo for srtwc286 | Which access level do you need for srtwc286? | PASS | v15 |
| 2 | 1 | I found 3 promotions for srtwc286. | PASS (Office promotions listed) | v15 |
| 3 | 2 | I found 3 promotions for srtwc286. | PASS (Dealer promotions listed, NOT the menu again) | v15 |
| 4 | 3 | I found 3 promotions for srtwc286. | PASS (End user promotions listed) | v15 |

This is the exact owner-found shape from B3 (PLAN-chatbot-focus-multi-domain.md, S6 review):
a HIT reply prints numbered promotion rows after "1", and "2" still resolves against the TIER
menu (dealer), not against the promotion file names the HIT reply printed. Confirmed fixed.

Screenshots: `s6-b.png` (1280), `s6-b-375.png` (375).

### Chain C - roster survives a declined escalate offer

| Step | Message | Reply (first line) | Result | Version |
|---|---|---|---|---|
| 1 | stock SRTWT2643 | Couldn't find "SRTWT2643" (product). Did you mean: | PASS | v15 |
| 2 | 2 | Here's what you want: | PASS (SRTWT2633 + "escalate to purchasing team?") | v15 |
| 3 | no | Escalation declined. | PASS | v15 |
| 4 | 1 | Here's what you want: | PASS (SRTWT2632, roster survived the decline) | v15 |

Screenshot: `s6-c.png`.

### Chain D - yes consumes the merged question

| Step | Message | Reply (first line) | Result | Version |
|---|---|---|---|---|
| 1 | stock SRTWT2643 | Couldn't find "SRTWT2643" (product). Did you mean: | PASS | v15 |
| 2 | 1 | Here's what you want: | PASS (SRTWT2632 + "escalate to purchasing team?") | v15 |
| 3 | yes | Your request is out of the scope of my ability and require human assistance. | PASS (escalation ran, "...from purchasing team") | v15 |
| 4 | 2 | Here's what you want: | PASS on the primary claim - see note | v15 |

Note on step 4: the instruction's expectation was "a new-message reply (clarifier or search)".
The actual reply was "Here's what you want: - product: SRTWT2632" - the SAME product as step 2,
not SRTWT2633 (the roster's option 2). Recorded verbatim: "2" was NOT resolved as a pick against
the original 3-row roster (the primary invariant under test - the roster was consumed by "yes"
and does not re-arm), but the reply is a continuation off the still-alive `focus.products`
(SRTWT2632) rather than a clarifier or a fresh search, since a bare "2" carries no product name
of its own once there is no open question to resolve it against. Marked PASS on the stated
invariant (must NOT re-pick SRTWT2633); the exact shape of the fallback reply differs from the
"clarifier or search" guess in the brief.

Screenshot: `s6-d.png`.

### Chain E - topic_reset clears the roster

| Step | Message | Reply (first line) | Result | Version |
|---|---|---|---|---|
| 1 | stock SRTWT2643 | Couldn't find "SRTWT2643" (product). Did you mean: | PASS | v15 |
| 2 | 1 | Here's what you want: | PASS (SRTWT2632 + "escalate to purchasing team?") | v15 |
| 3 | another one | Sure - do you want to switch to SRTWT2633 or SRTWT2634? | FAIL - see defects below | v15 |
| 4 | 2 | Could you share the options you're choosing from? | PASS (NOT a re-pick) | v15 |

Defects found on step 3, recorded verbatim (screenshot `s6-e.png` shows both bubbles):

1. **Two reply bubbles were produced for the one "another one" message.** First bubble, tagged
   `low_signal`: "Sure - do you want to switch to SRTWT2633 or SRTWT2634?" (ASCII hyphen).
   Second bubble, untagged (no message_type chip shown), directly below it: "Sure -- do you want
   to switch to SRTWT2633 or SRTWT2634?" using an EM DASH (U+2014) in place of the hyphen -
   the exact character `sanitize_em_dash` in `tail/compile_state.py` exists to fold, and the
   hard rule ("NEVER use em-dashes ... in any writing") forbids reaching a customer at all.
2. The reply itself deviates from "a clarifier asks which product": it names the two OTHER
   original roster members (SRTWT2633, SRTWT2634) rather than asking generically which product,
   which reads as a different (pre-existing, not part of this slice) low-signal/did-you-mean
   retry mechanism rather than the D19 "topic_reset clears the roster" trace this chain targets.

Step 4 still passed on its own primary claim (a bare "2" after this exchange did not resolve
against the original roster's option 2 = SRTWT2633), so the underlying open_question WAS
cleared by the topic_reset turn - but the turn 3 reply itself is a defect (duplicate bubble +
em dash) that needs its own fix, filed here rather than silently worked around.

Screenshot: `s6-e.png`.

### Chain F - roster survives a casual turn

| Step | Message | Reply (first line) | Result | Version |
|---|---|---|---|---|
| 1 | stock SRTWT2643 | Couldn't find "SRTWT2643" (product). Did you mean: | PASS | v15 |
| 2 | 1 | Here's what you want: | PASS (SRTWT2632 + "escalate to purchasing team?") | v15 |
| 3 | thanks | You're welcome! Happy to help. | PASS (casual reply, low_signal) | v15 |
| 4 | 2 | Here's what you want: | PASS (SRTWT2633, roster survived the casual turn) | v15 |

Screenshot: `s6-f.png`.

## Console / network

No browser console errors or uncaught exceptions across the whole run (`agent-browser errors`
checked after chain A setup and again at the end - empty both times).
