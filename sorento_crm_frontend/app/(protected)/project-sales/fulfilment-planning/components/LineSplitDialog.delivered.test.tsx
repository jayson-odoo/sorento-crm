/**
 * OI-LINE-SPLIT owner hand test 18 Oct (AC-A3): a line delivered in full is listed read-only so
 * the sheet matches the Excel: QTY and DELIVERY DATE as values, "Delivered 301" in CHANGE
 * QUANTITY, no grip, not offered in the AUTOCOUNT LINE select, not a drop target.
 */
import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  addBtn,
  block,
  onSel,
  ownerCase,
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

function withDelivered() {
  const p = ownerCase();
  p.lines.push({
    ...wireLine(32, 'CSK14B', 0, '2026-09-20', { delivered_qty: 301, now_qty: 0 }),
    delivered_in_full: true,
  } as never);
  return p;
}

const focused = () => (document.activeElement ?? document.body) as HTMLElement;
const press = (key: string, code: string = key) => fireEvent.keyDown(focused(), { key, code });

beforeEach(() => {
  vi.clearAllMocks();
  getLineSplits.mockResolvedValue(withDelivered());
});

describe('a line delivered in full', () => {
  it('is listed with QTY 301, DELIVERY DATE 20/09/2026 and "Delivered 301" in CHANGE QUANTITY', async () => {
    await renderDialog();
    await sheet();
    const text = block(32).textContent ?? '';
    expect(text).toContain('301'); // QTY = delivered_qty (base_qty is 0)
    expect(text).toContain('20/09/2026');
    expect(text).toMatch(/Delivered 301/);
    expect(text).not.toMatch(/Added in AutoCount/);
  });

  it('has no grip, no split cells and no "+ Split"', async () => {
    await renderDialog();
    await sheet();
    await screen.findByTestId('split-line-32');
    expect(screen.queryByRole('button', { name: 'Drag line 32' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Split line 32 quantity' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Split line 32 date' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Add a split to line 32' })).toBeNull();
  });

  it('is not offered in another line AUTOCOUNT LINE options', async () => {
    await renderDialog();
    await sheet();
    await splitLine(480);
    typeQty(480, 1, '14');
    fireEvent.click(addBtn(480));
    fireEvent.click(onSel(480, 2));
    const labels = (await screen.findAllByRole('option')).map((o) => (o.textContent ?? '').trim());
    expect(labels.some((l) => /^Line 32\b/.test(l)), labels.join('|')).toBe(false);
    expect(labels.some((l) => /^Line 608\b/.test(l))).toBe(true);
  });

  it('is not a drop target: keyboard targets skip it and it is never highlighted', async () => {
    await renderDialog();
    await sheet();
    const handle = screen.getByRole('button', { name: 'Drag line 480' });
    act(() => handle.focus());
    fireEvent.keyDown(handle, { key: ' ', code: 'Space' });
    await waitFor(() => expect(screen.getByTestId('drop-cancel')).toBeInTheDocument());
    const over = () =>
      ['split-line-32', 'split-line-608', 'split-line-752'].filter(
        (id) => screen.getByTestId(id).getAttribute('data-over') === 'true',
      );
    press('ArrowDown');
    expect(over()).toEqual(['split-line-608']);
    press('ArrowDown');
    expect(over()).toEqual(['split-line-752']);
    press('ArrowUp');
    press('ArrowUp');
    press('ArrowUp');
    expect(over()).not.toContain('split-line-32');
    press('Escape');
    void within;
  });
});
