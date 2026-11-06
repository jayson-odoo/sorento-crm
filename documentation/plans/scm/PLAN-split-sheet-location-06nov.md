# PLAN: Review split shows the line's own location (SPLIT-SHEET-LOCATION)

Status: in progress. Small fix track (one coder, one reviewer, no migration).

## Journey

Owner, 6 Nov: the Fulfilment Planning board shows SO429664 line SRTWT8239-GM at "BRW-BB" (its
AutoCount line location), but "Confirm SO429664" step 1 "Review split" shows "BRW". The sheet must
show the line's own AutoCount location, same as the board.

## Cause

`LineSplitService.line_facts` (`app/services/project_line_split_service.py`) computed
`location = line.stock_location or <core warehouse code>`. The project line's `stock_location` is
written by OI import / confirm paths and can be a pool/group code ("BRW"). The board reads
`fact.own_code` = core SO line warehouse (`project_supply_service.py` `own_code`), and
`ProjectOrderInquiryService._stock_location` names the core warehouse as the line's own location.

## Fix

`line_facts` prefers the core line's warehouse code; `line.stock_location` is only a fallback for
a line with no reconciled core warehouse (otherwise the cell would be blank).

## Consumers of `LineFacts.location` (behaviour after the fix)

- Split sheet GET payload `location` and its sort key (item, location, line no): now the core code.
- Save validation "a split can only sit on a line of the same item and location": compares core
  codes. Two lines at the same AutoCount warehouse are now always compatible even if their
  projects `stock_location` differ; lines at different AutoCount warehouses that share a pool
  code are no longer compatible (correct: they are different places).
- Confirm handover email row `stock_location` (`project_order_inquiry_service.py`): reads
  `f.line.stock_location or f.location`, so unchanged whenever stock_location is set.

## Tests

`tests/scm/test_split_sheet_location.py`: a line whose `stock_location` is a different code from
its core warehouse reads the core code on the sheet (red before the fix).
