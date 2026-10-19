/**
 * OI-LINE-SPLIT owner round 18 Oct (AC-A2, AC-A2b, AC-A3, AC-A5, F1): the sheet presents a change the
 * way the handover email does, QTY | NEW QTY | DELIVERY DATE | NEW DATE, there is no AUTOCOUNT LINE
 * column or select, and a split still reaches another line by drag only.
 * Shaped like SO417636 CSK14B BRW-BB; the customer is a placeholder.
 * F6 (drag a "N left" chip onto line 608 gives "+N from line 480") is proven by
 * LineSplitDialog.drag.test.tsx "the N left chip makes a new split of N at the target".
 */
import { fireEvent, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  addBtn,
  block,
  dateIn,
  qty,
  remarkIn,
  renderDialog,
  sheet,
  splitLine,
  typeQty,
  wireLine,
} from '@/test-mocks/lineSplitSheetKit';

const { getLineSplits, saveLineSplits } = vi.hoisted(() => ({
  getLineSplits: vi.fn(),
  saveLineSplits: vi.fn(),
}));
vi.mock('@/app/(protected)/project-sales/_shared/services/lineSplitService', () => ({
  getLineSplits: (...a: unknown[]) => getLineSplits(...a),
  saveLineSplits: (...a: unknown[]) => saveLineSplits(...a),
}));
vi.mock('@/lib/toast', () => ({
  toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn(), warning: vi.fn() }),
}));

function case417636() {
  return {
    pso_id: 'pso-417636',
    so_number: 'SO417636',
    so_date: '2026-09-03',
    customer: 'PLACEHOLDER CUSTOMER',
    project: 'PLACEHOLDER PROJECT',
    lines: [
      {
        ...wireLine(32, 'CSK14B', 0, '2026-09-20', { delivered_qty: 301, now_qty: 0 }),
        delivered_in_full: true,
      },
      wireLine(480, 'CSK14B', 417, '2026-10-20', {
        now_qty: 14, now_date: '2026-09-20', pending_change: true,
        new_qty: 14, new_date: '2026-09-20',
      }),
      wireLine(608, 'CSK14B', 192, '2026-11-20', {
        now_qty: 632, pending_change: true, new_qty: 632, new_date: null,
      }),
      wireLine(752, 'CSK14B', 504, '2026-12-20', {
        now_qty: 649, now_date: '2027-01-02', pending_change: true,
        new_qty: 649, new_date: '2027-01-02',
      }),
      // AutoCount added this line: base 0, no base date
      wireLine(800, 'CSK11A', 0, null, {
        now_qty: 335, now_date: '2027-01-02', pending_change: true,
        new_qty: 335, new_date: '2027-01-02',
      }),
    ],
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  getLineSplits.mockResolvedValue(case417636());
});

/** [QTY, NEW QTY, DELIVERY DATE, NEW DATE] of a line's first row, found by header text. */
async function cells(no: number) {
  const table = await sheet();
  const heads = within(table)
    .getAllByRole('columnheader')
    .map((h) => (h.textContent ?? '').trim().toLowerCase());
  const tds = Array.from(block(no).querySelector('tr')!.querySelectorAll('td'));
  return ['qty', 'new qty', 'delivery date', 'new date'].map((h) => {
    const i = heads.indexOf(h);
    expect(i, `column "${h}" exists`).toBeGreaterThanOrEqual(0);
    return (tds[i]?.textContent ?? '').trim();
  });
}

describe('header', () => {
  it('reads Line, SO date, S/O no, Item code, Location, Qty, New qty, Delivery date, New date, Change quantity, Change date, Remark, Balance', async () => {
    await renderDialog();
    const heads = within(await sheet())
      .getAllByRole('columnheader')
      .map((h) => (h.textContent ?? '').trim().toLowerCase())
      .filter(Boolean);
    expect(heads).toEqual([
      'line', 'so date', 's/o no', 'item code', 'location', 'qty', 'new qty',
      'delivery date', 'new date', 'change quantity', 'change date', 'remark', 'balance',
    ]);
    expect(heads).not.toContain('autocount line');
  });
});

describe('QTY | NEW QTY | DELIVERY DATE | NEW DATE per line', () => {
  it('delivered in full: 301, empty, 20/09/2026, empty, and "Delivered 301" stays', async () => {
    await renderDialog();
    expect(await cells(32)).toEqual(['301', '', '20/09/2026', '']);
    expect(block(32).textContent).toMatch(/Delivered 301/);
  });

  it('480: 417, 14, 20/10/2026, 20/09/2026', async () => {
    await renderDialog();
    expect(await cells(480)).toEqual(['417', '14', '20/10/2026', '20/09/2026']);
  });

  it('608: quantity moved only: 192, 632, 20/11/2026, empty', async () => {
    await renderDialog();
    expect(await cells(608)).toEqual(['192', '632', '20/11/2026', '']);
  });

  it('752: 504, 649, 20/12/2026, 02/01/2027', async () => {
    await renderDialog();
    expect(await cells(752)).toEqual(['504', '649', '20/12/2026', '02/01/2027']);
  });

  it('a line AutoCount added: 0, 335, "-", 02/01/2027', async () => {
    await renderDialog();
    expect(await cells(800)).toEqual(['0', '335', '-', '02/01/2027']);
  });

  it('no "AutoCount now" or "Added in AutoCount" text anywhere', async () => {
    await renderDialog();
    await sheet();
    expect(document.body.textContent).not.toMatch(/AutoCount now/);
    expect(document.body.textContent).not.toMatch(/Added in AutoCount/);
  });
});

describe('no AUTOCOUNT LINE select, drag only', () => {
  it('a split row and a "+ Split" row carry no AutoCount line control and Enter opens no listbox', async () => {
    await renderDialog();
    await sheet();
    await splitLine(480);
    typeQty(480, 1, '14');
    fireEvent.click(addBtn(480));
    expect(
      screen.queryAllByRole('combobox', { name: /^AutoCount line, line \d+ split \d+$/ }),
    ).toHaveLength(0);
    for (const el of [qty(480, 2), dateIn(480, 2), remarkIn(480, 2), qty(480, 1)]) {
      fireEvent.keyDown(el, { key: 'Enter' });
      expect(screen.queryByRole('listbox')).toBeNull();
    }
    expect(screen.queryByRole('combobox', { name: /AutoCount line/i })).toBeNull();
  });
});
