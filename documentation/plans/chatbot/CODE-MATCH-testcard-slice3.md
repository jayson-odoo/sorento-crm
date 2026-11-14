# CHATBOT-CODE-MATCH slice 3: 10:00 test card (Chatbot Console, dry run, no WhatsApp send)

PR #2370, slice 3: a code close to a registered product set offers the set first, then its member products (from the
set's own member list), up to 3. Picking the set answers it exactly like typing the set code. Same for staff and
dealers, for one code or several in a message. The "X" family rule is unchanged (moved to slice 5, crew ruling).
Pick a registered set from Product Sets in the test copy (the review's example is CWC604-P-RL).

| # | Contact | Type | Before (main) | After (this slice) |
| --- | --- | --- | --- | --- |
| 1 | dealer | `CWC604RL x 2` (set code with a part missing) | "Please refer to your salesman." or a list of unrelated codes | "Couldn't find CWC604RL. Did you mean:" 1. CWC604-P-RL (the set) 2-3. its member products; quantity 2 kept |
| 2 | dealer | reply `1` to question 1 | n/a | the set answered as if CWC604-P-RL had been typed (its members' stock, "How many units for each?" when no quantity is set) |
| 3 | staff | `CWC604RL x 2` | did-you-mean without the set | `Couldn't find "CWC604RL" (product). Did you mean` the set first, then members; escalation offer kept |
| 4 | dealer | `CWC604PRL stock` (set code without dashes) | answered | answered, unchanged |
| 5 | staff | `<any found code> x 1, CWC604RL x 2` | "Couldn't find: CWC604RL." with no offer | the found code answered; CWC604RL offered the same list as in question 3 |

Not offered: a set with a member the asking dealer may not see.
