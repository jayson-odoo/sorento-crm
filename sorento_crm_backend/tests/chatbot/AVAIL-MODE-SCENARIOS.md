# Availability-mode stock asks: scenario catalogue

Every way a contact asks about stock, and what availability mode (a dealer: "got stock / no
stock", never our quantities) replies, beside what full mode (staff: compact / detailed)
does. Each `S` id is a test in `test_avail_mode_scenarios.py` (same folder), which asserts
the reply word for word, and a row on the owner-approved page
`documentation/mockups/avail-mode-scenarios/index.html` (v2, approved 2 Oct 2026).

Plan and rulings: `documentation/plans/chatbot/PLAN-avail-mode-replies-02oct.md`.

`R` = "Please refer to your salesman." X = the product's max quantity, else its own
category's, else 0. Available = on hand in the contact's allowed locations minus open SO.

## Rules

1. One line per product, "CODE x Q:", then ✅ (got stock) or ❌ (no stock). Never the words.
2. 1 <= available < Q and Q <= X: `✅ N available.` Q > X: `🚫 the quantity is more than what I can confirm here.` with no count.
3. ETA ask: `CODE: ETA dd/mm/yyyy` (or `ETA not confirmed yet`), one line per product.
4. A picker never offers "all" and refuses a bare "all" / "all of them" / "semua" (the list stays open). Typing every number is a pick.
5. Several codes: answered lines (asked order), then `Couldn't find: X, Y.`, then at most one question. Every vague code's list is in that one question, numbered on from the list before it. A code named twice adds up.

## One code

| Id | Dealer | Bot (availability) | Full mode |
| --- | --- | --- | --- |
| S01 | SRT5674 x 50 (100 on hand) | `SRT5674 x 50: ✅ R` | Total on hand per product |
| S02 | SRT5674 x 50 (30 on hand, X 100) | `SRT5674 x 50: ✅ 30 available. R` | same |
| S03 | SRTW2000 x 150 (0, shipment 19/10) | `SRTW2000 x 150: ❌ ETA 19/10/2026.` | same |
| S04 | SRT5674 x 5 (0, nothing incoming) | `SRT5674 x 5: ❌ No incoming. R` | same |
| S05 | CWCX604 x 300 (X 200) | `CWCX604 x 300: 🚫 the quantity is more than what I can confirm here. R` | no cap in full mode |
| S06 | CWCX604 x 5 (X not set) | same 🚫 line | no cap |
| S07 | SRT5674 got stock? / 50 | `How many units of SRT5674?` / the S01 line | no quantity asked |
| S08 | SRTWC287-S x 3 (prefix of one code) | `SRTWC287-S-150 x 3: ✅ R` | that code's total |
| S09 | srtwc286 x 10 / 2 | `SRTWC286 x 10: which one?` + 1-10 / `SRTWC286-SH-150 x 10: ✅ R` | every match listed |
| S10 | check stock srtwc286 / 2 | `SRTWC286 matches 10 products. Which one?` + 1-10 / `How many units of SRTWC286-SH-150?` | every match listed |
| S11 | ELP3753 x 10 / yes | `Couldn't find ELP3753. Did you mean ELP3754?` / `ELP3754 x 10: ✅ R` | did-you-mean |
| S12 | FOO99 x 1 | `Couldn't find: "FOO99" (product).` + R | same sentence |

## ETA asks

| Id | Dealer | Bot | Full mode |
| --- | --- | --- | --- |
| S14 | ETA SRTW2000? | `SRTW2000: ETA 19/10/2026` + R | shipments with container and quantity |
| S15 | ETA SRTW2000 and MWT5727SS-CR | one line each, `MWT5727SS-CR: ETA not confirmed yet`, + R | same |
| S16 | ETA SRTW2000 and FOO99 | ETA line, `Couldn't find: FOO99.`, R | "I could not find FOO99." |

## Several codes

| Id | Dealer | Bot |
| --- | --- | --- |
| S17 | SRT5674 x 50, CWCX604 x 40, SRTW2000 x 10 | three lines, asked order |
| S18 | SRT5674 x 5, FOO99 x 1 | S01-style line, `Couldn't find: FOO99.` |
| S19 | SRT5674 x 5, SRTWC287-S x 3 | two answered lines |
| S20 | SRT5674 x 5, srtwc286 x 10 / 2 | answered line + picker / the picked line |
| S21 | srtwc286 x 10, srtwc6022 x 4 / 2 and 11 | both lists in one message (1-10, 11-12) / both answered |
| S21b | same / 2 / 12 | answered line + the SRTWC6022 list again (11-12) / answered |
| S22 | srtwc286 x 10, FOO99 x 1 | `Couldn't find: FOO99.` + picker |
| S22b | SRT5674 x 5, srtwc286 x 10, srtwc6022 x 4, FOO99 x 1 | answered, missing, both lists |
| S23 | FOO99 x 1, BAR12 x 2 | `Couldn't find: "FOO99" (product), "BAR12" (product).` + R |
| S24 | SRT5674 x 2, SRT5674 x 3 | `SRT5674 x 5: ✅ R` |
| S25 | SRT5674, CWCX604 / 1. 10, 2. 5 | point form `How many units for each?` / two lines |
| S26 | SRT5674, CWCX604, FOO99 | `Couldn't find: FOO99.` + point form |
| S27 | SRT5674 x 5 and CWCX604 / 7 | answered line + `How many units of CWCX604?` / `CWCX604 x 7: ✅ R` |
| S28 | SRT5674, CWCX604 / 10 | point form / both x 10 |
| S29 | SRT5674 x 50, SRTW2000 x 150 | `✅ 30 available` line + `❌ ETA` line |

Full mode answers every code with its quantities at once: no quantity question, no picker
for a family (every match is listed), and the shared miss sentence for codes not found.

## Picker replies (over `srtwc286 x 10`)

| Id | Dealer | Bot | Full mode |
| --- | --- | --- | --- |
| S30, S31, S34 | all / all of them / semua / all pls | `Please reply with the number of the code you need.` (list stays open) | "all" picks every option |
| S32 | 1,2,...,10 | ten answered lines | same |
| S33 | all, then 2 | refusal, then the picked line | - |
| S35 | 1 and 2 | two answered lines | same |
| S36, S37 | 2 of 3 / i want 2 of the third one / 2 of 3rd product | `SRTWC286-SH-200 x 2: ...` | - |
| S38 | 2 of 1 and 5 of 3 | two lines, x 2 and x 5 | - |
| S39 | 2 of 2 (after "x 10") | `SRTWC286-SH-150 x 2: ...` (the pick's quantity wins) | - |
