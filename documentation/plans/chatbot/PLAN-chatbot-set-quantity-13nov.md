# PLAN: CHATBOT-SET-CODES B (slice 2): a dealer's set + quantity answers each part

Status: Plan (card in the PR body; red tests next). Track: size M, lead pattern, cloud lane. Stacked on PR #2395.

Owner ruling 13 Nov ~17:00 (verbatim): "if deleae say x 2 then it should answer for WCX604 2 got stock anot, WCY604 2
got stock anot ah". Crew defaults for the edges (13 Nov): a part whose set quantity is more than 1 multiplies; one part
short says which part is short; no quantity typed keeps today's reply.

## Rule

A dealer (availability-only contact) who types a registered set WITH a quantity gets no "How many units for each?"
question. The bot answers availability for EACH part of the set at (the part's quantity in the set x the typed
quantity), one line per part, in the same wording as a normal single-code availability answer ("<code> x <n>: Got
stock." / "Only <available> got stock." / "No stock, ETA ..."). The parts come from the set membership table in its
order. Nothing changes for staff, for a dealer set ask with no quantity, or for a single product.

## Examples (dev catalogue shapes)

| Typed (dealer) | Today (prod and main) | After |
| --- | --- | --- |
| `CWC604-P-RL x 2` (pan CWCX604-P-RL, cistern CWCY604, 1 each) | How many units for each? 1. CWCX604-P-RL 2. CWCY604 | CWCX604-P-RL x 2: Got stock. / CWCY604 x 2: Got stock. |
| `CWC605RL x 1` (set CWC605-RL; longer sets -SOFT/-NEW/-WEPLS exist) | How many units for each? 1. CWCX605-RL 2. CWCY605 | CWCX605-RL x 1: Got stock. / CWCY605 x 1: Got stock. (no sibling set) |
| `CWC604-P-RL x 3`, cistern has 1 in stock | How many units for each? ... | CWCX604-P-RL x 3: Got stock. / CWCY604 x 3: Only 1 got stock. |

Edges: a part with set quantity 2 and typed 3 is asked at 6; a discontinued part keeps its existing discontinued line;
no quantity typed: today's question; picking an offered set after "x 2" answers the same way (the pick carries 2).

## Reuse

The pick path already stamps a typed quantity per row (`turn/apply.py` ~3071, `requested_quantities`); R3 skips set
rows there. The fix carries the set's typed quantity onto its member rows (x member quantity) through that same
stamping, so the availability renderer answers each part as it answers a single code.

## Gate

Red-first with the 2 offline cases of the 13 Nov release check (lone set x 2, set with siblings x 1), plus the short
part and the multiplied part; kill test; reviewer; crew-tests incl. full tests/chatbot; frozen past owner-FAIL set LIVE
x3 run by crew before crew-done; before/after card for the owner's hand test.
