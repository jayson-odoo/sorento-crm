/**
 * OI-LINE-SPLIT owner round 2 (AC-A5 "Pending change default", AC-A4): "+ Split" on a pending,
 * unsplit line starts NEW QTY @ NEW DATE plus the rest; clicking the value cell stays one row.
 * Shaped like SO417636 CSK14B; the customer is a placeholder.
 */
import { fireEvent, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  addBtn,
  balance,
  block,
  dateIn,
  qty,
  queryQty,
  remainQty,
  renderDialog,
  sheet,
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

function pendingCase() {
  return {
    pso_id: 'pso-417636',
    so_number: 'SO417636',
    so_date: '2026-09-03',
    customer: 'PLACEHOLDER CUSTOMER',
    project: 'PLACEHOLDER PROJECT',
    lines: [
      wireLine(480, 'CSK14B', 417, '2026-10-20', {
        now_qty: 14, now_date: '2026-09-20', pending_change: true,
        new_qty: 14, new_date: '2026-09-20',
      }),
      wireLine(608, 'CSK14B', 192, '2026-11-20'),
    ],
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  getLineSplits.mockResolvedValue(pendingCase());
});

describe('+ Split on a pending, unsplit line', () => {
  it('line 480 gives 14 @ 20/09/2026 ADVANCE, then 403 @ 20/10/2026; balance 0 ticked; focus in row 2 qty', async () => {
    await renderDialog();
    await sheet();
    fireEvent.click(addBtn(480));
    expect(qty(480, 1).value).toBe('14');
    expect(dateIn(480, 1).value).toBe('20/09/2026');
    expect(qty(480, 2).value).toBe('403');
    expect(dateIn(480, 2).value).toBe('20/10/2026');
    expect(queryQty(480, 3)).toBeNull();
    const row1 = qty(480, 1).closest('tr') as HTMLElement;
    expect(within(row1).getByText('ADVANCE')).toBeInTheDocument();
    expect(balance(480).textContent).toMatch(/^\s*0/);
    expect(balance(480).textContent).not.toMatch(/left/);
    expect(document.activeElement).toBe(qty(480, 2));
  });

  it('a line with no pending change gives its base row plus a 0 row as before', async () => {
    await renderDialog();
    await sheet();
    fireEvent.click(addBtn(608));
    expect(qty(608, 1).value).toBe('192');
    expect(dateIn(608, 1).value).toBe('20/11/2026');
    expect(qty(608, 2).value).toBe('0');
    expect(dateIn(608, 2).value).toBe('20/11/2026');
  });

  it('guard AC-A4: clicking line 480 CHANGE QUANTITY value gives ONE split row 417 @ 20/10/2026', async () => {
    await renderDialog();
    await sheet();
    fireEvent.click(remainQty(480));
    await screen.findByLabelText('Quantity, line 480 split 1');
    expect(qty(480, 1).value).toBe('417');
    expect(dateIn(480, 1).value).toBe('20/10/2026');
    expect(queryQty(480, 2)).toBeNull();
    void block;
  });
});
