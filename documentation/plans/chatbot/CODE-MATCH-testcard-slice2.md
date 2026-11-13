# CHATBOT-CODE-MATCH slice 2: 10:00 test card (Chatbot Console, dry run, no WhatsApp send)

PR #2370, slice 2: close codes that hold every part the customer typed are offered first. Parts are the typed code split
at dashes, spaces and letter/digit changes ("SRTWC286-150" -> SRTWC, 286, 150). Same order for staff and dealers, for
one code or several in a message. Codes are catalogue codes; pick ones that exist in the test copy.

| # | Contact | Type | Before (main) | After (this slice) |
| --- | --- | --- | --- | --- |
| 1 | staff | `SRTWC286-150` | "Did you mean: 1. SRTWC286-SH-150 2. SRTWC286-SH 3. SRTWC286-SH-NEW-150" | 1. SRTWC286-SH-150 2. SRTWC286-SH-NEW-150 3. SRTWC286-SH (the two codes holding "150" first; the family still leads) |
| 2 | dealer | `Swtwc8354-SH-UF x 3` | close codes in similarity order | same codes; any holding 8354, SH and UF are listed before one missing a part |
| 3 | staff | `8152 stock` (short token, many codes) | which-one list of every match | unchanged: every match listed |
| 4 | dealer | `BT015SSCR stock` (dash missing only) | answered directly | unchanged: answered directly |
| 5 | staff | two misses in one message, e.g. `SRTWC286-150 x 1, Swtwc8354-SH-UF x 2` | each list in similarity order | each list ordered as it is when asked alone |

After each turn, the Console trace's `code_candidates` entry lists the offered codes in the new order.
