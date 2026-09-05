/**
 * The cell breakdown dialog's Stock tab has exactly ONE vertical scroll region.
 *
 * Reported hands-on, 5 Sep 2026: on the board cell for SRTWHBWP / 27 Feb 2023, with the
 * "Site pool subtotal" row expanded, the documents table's column header was hidden under the
 * rows above it and the wheel would not move the table the pointer was over. Measured in a
 * browser at 1440x900 there were FOUR nested `overflow-y: auto` boxes stacked on that tab, all
 * four overflowing at the same time:
 *
 *   dialog body            clientHeight 652, scrollHeight 712
 *   cell-stock-table       clientHeight 448, scrollHeight 832   (`max-h-[50vh]`)
 *   stock-documents-panel  clientHeight 315, scrollHeight 662   (`max-h-[35vh]`)
 *   data-grid-scroller     clientHeight 580, scrollHeight 1045
 *
 * The documents grid's box is 580px tall inside a 315px window, so its own sticky header sat
 * 33px above the visible top of the panel that clipped it: present in the DOM, invisible to the
 * reader. `DialogBody` already owns a scroll viewport (`min-h-0 flex-1 overflow-y-auto`), so the
 * two inner caps are removed and it is the one region. This test is what keeps them off - a
 * `max-h-[..vh]` (or any fixed viewport-height bound) on either file puts a scrollport back
 * inside a scrollport, which is the exact defect.
 */
import fs from 'node:fs';
import { describe, it, expect } from 'vitest';

const DIR = 'app/(protected)/project-sales/fulfilment-planning/components';

/** Any fixed viewport-height bound - `max-h-[50vh]`, `h-screen`, `min-h-dvh`, ... */
const VIEWPORT_BOUND =
  /\[\d+(?:\.\d+)?[dls]?vh\]|(?<![\w-])h-screen(?![\w-])|min-h-screen/;

const FILES = [`${DIR}/CellStockTable.tsx`, `${DIR}/StockDocumentsPanel.tsx`];

describe('cell breakdown Stock tab: one scroll region', () => {
  it('neither the stock table nor the documents panel bounds itself to a slice of the viewport', () => {
    for (const file of FILES) {
      const offending = fs
        .readFileSync(file, 'utf8')
        .split('\n')
        .filter((line) => VIEWPORT_BOUND.test(line));
      expect(offending, file).toEqual([]);
    }
  });

  it('neither opens a vertical scrollport of its own', () => {
    for (const file of FILES) {
      const offending = fs
        .readFileSync(file, 'utf8')
        .split('\n')
        .filter((line) => /overflow-y-(auto|scroll)/.test(line));
      expect(offending, file).toEqual([]);
    }
  });

  it('the stock table keeps its horizontal scroll - the table is wider than the dialog', () => {
    const src = fs.readFileSync(`${DIR}/CellStockTable.tsx`, 'utf8');
    expect(src).toMatch(/overflow-x-auto/);
  });

  it('the stock table header is not sticky - it would fight the dialog toolbar pinned at top-0', () => {
    const src = fs.readFileSync(`${DIR}/CellStockTable.tsx`, 'utf8');
    const headCell = src.match(/const HEAD_CELL =\n\s*'([^']*)'/);
    expect(headCell, 'HEAD_CELL constant not found').not.toBeNull();
    expect(headCell?.[1]).not.toMatch(/(?<![\w-])sticky(?![\w-])/);
  });
});
