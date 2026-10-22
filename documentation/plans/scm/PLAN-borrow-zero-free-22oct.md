# PLAN: Borrow lists locations with 0 free stock (BORROW-ZERO-FREE, 22 Oct 2026)

Status: in progress, review + browser pass (small fix track: under ~300 lines, no migration,
no auth/RBAC change).
Lane: BORROW-ZERO-FREE, branch `crew/borrow-zero-free`, base origin/main d04536d258.
UAC: `borrow-zero-free-22oct-acceptance-criteria.md` (alongside).

## Journey

Owner, 22 Oct 11:44, prod screenshot SO401624 line 224 (BRW-BB, 0 available): the Borrow
section says "No other location or project holds free stock of this item." He wants Borrow to
list locations even when they hold 0 (or negative) free stock, "not available also can borrow",
on every fulfilment planning screen, including the Decide control's Borrow location dropdown.

Rulings carried in: own location always in Borrow (BORROW-OWN-LOC, 13 Oct); quantities are never
capped by CRM stock (what is not free is recorded short at Confirm, OI-CLOSED-LINE 12 Oct).

## Diagnosis (step 1, dev copy `sorento_cagent_stack`, read-only)

SO401624 line 224 = SRTWB242, 501 open, own location BRW-BB, required 2027-06-07, lead time 90 d.
Reserve window end = 22 Oct 2026 + 90 + 14 (`RESERVE_BUFFER_DAYS`) = 3 Feb 2027, so
`outside_reserve_window` is True (`project_supply_service.py:1560`) and both readers blank the
whole donor list: board `project_fulfilment_board_service.py:2957-2961` / `:3003-3009`, sheet
`project_supply_service.py:5081-5083`. That gate, not the free>0 filter, is what empties the
owner's screenshot. Ungated, `_borrow_candidates` on the dev copy returns MWH-BB (43 free) and
the own BRW-BB (0 free, available -1294).

Owner ruling (b), 22 Oct ~11:00: drop the window gate for the Borrow LIST only, on the board,
the per-order sheet and the Decide Borrow dropdown. The ladder still skips the borrow rungs
beyond the window, so auto-proposals and the "borrowing is possible from" trail note are
unchanged. Confirm must accept a hand-picked Borrow on such a line (proved end to end).

## Change (step 2)

1. Backend `_borrow_candidates` (`project_supply_service.py:10607-10612`): drop `qty > _ZERO`
   on the free-stock rows. Every location outside the Reserve pool that carries a `stock` row
   for the item at a drawable (planning or pool) location is listed, `free_qty` 0 when nothing
   is free; signed `available_qty` unchanged. `_ranked` gains a first key, "has free stock",
   so a 0-free row never takes the recommended head: availability nets what the book owes, not
   what is reserved or held, so a fully spoken-for pile can read more available than one with 7
   free (`test_fulfilment_board.py` covered-line test caught it). Every row listed before this
   lane had free > 0, so their order is unchanged.
2. Other-project holds (`:10645-10650`) keep `qty > _ZERO`: a hold is a PROJECT donor, and a
   held quantity of 0 (`held_qty_expr` caps at what is still owed, `:251-266`, so every
   delivered allocation reads 0) names a project that holds nothing. The location itself is
   already listed by item 1. Flagged to crew as a deliberate narrowing of the brief.
3. Decide control picker (`BoardDecideControl.tsx:141-147`): list every plain location
   candidate, not only `free_qty > 0` or the own location.
4. Decide composition (`_shared/lib/boardAmend.ts` `borrow_other`): what the picked location
   cannot cover rides on its plain location row and the line saves short, as the own location
   already does and as "Add a borrow" already does (`BorrowAddDialog.tsx` over-ask). Without it
   a 0-free pick skips every row ("only 0 free at X"), which is the cap the owner ruled out.
   Confirm already records a plain location borrow short (`project_supply_service.py:6773-6788`).
5. Ruling (b): board `project_fulfilment_board_service.py` (plannable and covered rows) and
   sheet `project_supply_service.py` `borrow_candidates` no longer blank on
   `outside_reserve_window`; the sheet still blanks an unplannable line. `_trail` reads the
   window itself, so the note and the walked rungs are unchanged. Confirm reads the window
   only for own-arrival credit (`:6178-6182`), never for a manual Borrow.
6. Unchanged on purpose: the trail note "borrowing is possible from" (board `:3471`, keeps
   free>0: never name a place with nothing free); Reserve "Add location" filter
   (`BoardLineDecisionPanel.tsx:292-301`).

## Tests (red first)

- pytest: a location outside the Reserve pool with a stock row at 0 free is a Borrow candidate
  (free 0, signed available); a location with stock still ranks ahead of it.
- pytest: a 0-free location never takes the recommended head from one with stock.
- pytest (ruling b): beyond the window the board (plannable + covered) and the sheet offer the
  list, the proposal is still a whole-line Buy, and a donor picked off the sheet confirms and is
  held (SO401624 line 224 shape: 441 due today + 174 d, 90 d lead).
- vitest: Decide Borrow-location picker lists a 0-free location; picking it saves the line as a
  location borrow carrying the whole quantity with the short warning (not skipped).

## Verification

Kill test on both; reviewer; agent-browser 1280 + 375 on the board and the per-order sheet;
laneboard hand-test script; crew report --handtest.
