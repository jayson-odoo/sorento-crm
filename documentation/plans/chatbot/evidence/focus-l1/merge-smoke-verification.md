# Merged-head smoke check - chatbot focus lane 1 (PR #863)

Head under test: feat/chatbot-focus at bf80b959a (main-merge + outstanding-report + fixes; CI green).
Stack: FE http://localhost:3081, BE :8081, MCP :8765. Browser: agent-browser headless, session l1-merge.
Contact: Jayson (preselected). Prompt version: v15 selected before every chain and confirmed on each reply
bubble. Navigated by sidebar: System > Messaging > Chatbot Console. Console reports "dry run, nothing
reaches WhatsApp". No console errors, no page errors during the run.

Purpose: confirm the main merge did not break the sticky-roster chains (A/B/C), and that main's
newly merged outstanding-report lane (#862) works on the five-key model (D/E).

## Results

| Chain | Step (message) | Reply first line | Version | Result |
| --- | --- | --- | --- | --- |
| A | `stock SRTWT2643` | `Couldn't find "SRTWT2643" (product). Did you mean:` (roster 1 SRTWT2632 / 2 SRTWT2633 / 3 SRTWT2634) | v15 | PASS |
| A | `1` | `Here's what you want:` (product: SRTWT2632; no stock/incoming/on order) | v15 | PASS |
| A | `2` | `Here's what you want:` (product: SRTWT2633; re-pick, not a re-answer of 2632) | v15 | PASS |
| A | `3` | `Stock details found for the requested products.` (SRTWT2634, 4 locations + incoming) | v15 | PASS |
| B | `promo for srtwc286` | `Which access level do you need for SRTWC286?` (1 Office / 2 Dealer / 3 End user) | v15 | PASS |
| B | `1` | `I found 3 promotions for SRTWC286.` (three OFFICE flyer PDFs) | v15 | PASS |
| B | `2` | `I found 3 promotions for SRTWC286.` (three DEALER flyer PDFs, NOT the menu again) | v15 | PASS |
| C | `incoming wc286` | `incoming search needs to be more specific. Multiple matches found.` (10-row picker, item 10 = SRTWC286-SH-NEW) | v15 | PASS |
| C | `10` | `I have attached the file(s) below.` (two SRTWC286-SH-NEW containers only, no sibling code named) | v15 | PASS |
| D | `SRTWT2634 outstanding` | `Product: SRTWT2634 / Customer: all / Location: all / Order date: all` then `*Delivery order outstanding*` block (6 DOs, DO qty 66, O/S 66, by location, by customer) then `Reply 1 for the delivery order list.` | v15 | PASS |
| E | `outstanding for chin` | `Which customer do you mean? Please choose:` (8-company picker: CHIN CHUN HARDWARE ...) | v15 | PASS |
| E | `1` | `Product: all / Customer: CHIN CHUN HARDWARE SDN BHD - [A/C I] / Location: all / Order date: all` then `*Delivery order outstanding*` block (2 DOs, DO qty 4, O/S 4, by location, by product) | v15 | PASS |

## Per-chain outcome

- Chain A (sticky did-you-mean roster): PASS. Re-picks 1/2/3 each resolve to the correct code
  (SRTWT2632 / 2633 / 2634); `2` re-picks SRTWT2633, not a re-answer of 2632.
- Chain B (promo tier menu): PASS. `1` returns Office flyers, `2` returns Dealer flyers, and `2`
  does NOT re-show the tier menu.
- Chain C (incoming 10-row picker): PASS. `10` answers SRTWC286-SH-NEW only (two containers); no
  sibling code (e.g. -NEW-P, -NEW-200) is named.
- Chain D (outstanding report reachable on five-key model): PASS. Feature is reachable in the
  console. For this contact the report renders the Delivery-order-outstanding block directly with a
  single-scope offer ("Reply 1 for the delivery order list"), and does NOT ask the SO-vs-DO scope
  question - the expected per-contact SO-key gate: contact Jayson lacks the sales-order key, so the
  SO figures and the scope question are gated off and only the DO outstanding is shown.
- Chain E (pick transition - the eight fixes): PASS via the customer picker. `outstanding for chin`
  armed the "Which customer do you mean?" picker; replying `1` closed the picker, survived its own
  pick, and carried the chosen customer (CHIN CHUN HARDWARE SDN BHD - [A/C I]) through into a fresh
  report scoped to that customer.

## Deviation recorded (not a chain failure)

On chain D the single-scope detail offer ("Reply 1 for the delivery order list") did not render the
per-DO detail row list when picked. First `1` echoed the offer line verbatim ("Reply 1 for the
delivery order list."); a second `1` re-ran the DO-outstanding summary report (product SRTWT2634
carried through) instead of the promised per-DO rows (DO Number / Customer / Product / Location /
DO Qty). The customer-picker transition in chain E worked cleanly, so the eight pick fixes are
exercised and pass; this detail-list-pick behaviour is noted for the captain.

## Evidence

- merge-A.png - chain A roster + three re-picks (1280 wide)
- merge-B.png - chain B Office then Dealer promos (1280 wide)
- merge-C.png - chain C 10-row picker + SRTWC286-SH-NEW answer (1280 wide)
- merge-D.png - chain D outstanding report (DO-only, SO gated) (1280 wide)
- merge-E.png - chain E customer picker + report scoped to picked customer (1280 wide)
