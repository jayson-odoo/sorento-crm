# UAC: PI header fields, convert repeat products, source files, async PL download

Plan: `PLAN-pi-header-fields-convert-fixes-24sep.md`. Status: GRILLED 24 Sep (R-A..R-D taken).

## Journey

Purchasing uploads a supplier's proforma invoice. The header block of the sheet names the B/L,
container and seal, often in one cell. The PI detail shows all three plus the consignee. When
the goods are ready, the buyer presses Convert to packing list once (header button), searches
the list if it is long, sees exactly the invoice's lines once each, and confirms. The packing
list opens with container, seal, SO (the B/L) and consignee filled. Download packing list adds
the file to My Downloads and the download history sits on the packing list.

## Header fields

- AC-H1 DAFUYUAN's cell `提单号 ：OOLU… 柜号 ：FSCU… 封条号：OOLLGZ7182` yields BL OOLU2339207730,
  Container FSCU9304169, Seal OOLLGZ7182 on the PI.
- AC-H2 NEW YANGGANG's `提单号：  柜号：FSCU8706420  封条：OOLLJN6147` yields BL empty, Container
  FSCU8706420, Seal OOLLJN6147.
- AC-H3 A cell with one `label：value` pair reads as today; a labelled value elsewhere on the
  sheet still wins first.
- AC-H4 The PI General tab shows Container, Seal, BL, Consignee in that order; empty ones "-".

## Header fields in the mapper (R-D)

- AC-F1 After a file lands, the mapper shows a "Header fields" section ABOVE the column grid
  listing every `label：value` pair found above the table (DAFUYUAN: 提单号, 柜号, 封条号, Date:, PI
  No.:) with the value as sample and the label as-is; a pair already known for this supplier is
  pre-filled.
- AC-F2 Field choices are PI number, Invoice date, BL, Container, Seal, Currency, Ignore;
  Consignee is not offered.
- AC-F3 Test saves header-field picks together with the column picks; the next upload from the
  same supplier folds the section into the "N of N mapped" summary.
- AC-F4 Mapping 柜号 -> Container and 封条号 -> Seal on DAFUYUAN, then Test, yields the three
  values split correctly (AC-H1) with no admin-page edit.

## Convert

- AC-C1 The dialog lists each invoice line once; DAFUYUAN = 15 rows, total qty 903, cartons 744.
- AC-C2 The packing list created has 15 shipment lines, qty 903; the fill bar reads 113.59 cbm
  of the chosen container.
- AC-C3 The dialog has a search box filtering by code or product; the Convert / Cancel footer
  stays visible above the table at a 800 px tall window.
- AC-C4 Only the header's Convert to packing list button exists; the Packing lists tab empty
  state has no button.
- AC-C5 "Carried onto the draft" names exactly what the packing list will receive.
- AC-C6 The packing list shows Container no, Seal no, SO (= the PI's BL) and Consignee = the
  PI's company, always (R-B); Shipper stays "-".
- AC-C7 Existing PIs with a repeated product are rebound by the backfill; the PR states the
  count on the prod copy.

## Source files

- AC-S1 One upload = one Source files row, with preview and download; the raw-name fallback
  row appears only when no file is linked.

## Download

- AC-D1 Download packing list enqueues an export, toasts, and the file appears in My Downloads
  with the packing list as its source; Download history on the packing list gear lists it.
- AC-D2 The worker renders the same workbook the sync export produced.
