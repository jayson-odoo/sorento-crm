/**
 * OI-LINE-SPLIT AC-G20 F2: the extra row comes from the saved plan, so a line whose splits
 * the draft has changed shows none. Customer is a placeholder.
 */
import { fireEvent, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  addBtn,
  block,
  qty,
  ownerCase,
  renderDialog,
  sheet,
  typeQty,
  wireSplit,
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

function saved() {
  const p = ownerCase();
  const l480 = p.lines.find((l) => l.line_id === 'L480')!;
  l480.splits = [
    wireSplit('s14', 14, '2026-09-20', 'L480'),
    wireSplit('s403', 403, '2026-10-20', 'L480'),
  ];
  const l752 = p.lines.find((l) => l.line_id === 'L752')!;
  Object.assign(l752, { extra_qty: 145, extra_remark: 'ORDER 145' });
  l752.splits = [
    wireSplit('s467', 467, '2027-01-02', 'L752'),
    wireSplit('s37', 37, '2026-11-20', 'L608'),
  ];
  return p;
}

beforeEach(() => {
  vi.clearAllMocks();
  getLineSplits.mockResolvedValue(saved());
});

const extraRow = (no: number) => block(no).querySelector('tr[data-extra-row]');

describe('AC-G20 F2 no stale extra row while drafting', () => {
  it('before any change 752 shows the 145 extra row', async () => {
    await renderDialog({}, 'pso-417636');
    await sheet();
    expect(extraRow(752)?.textContent).toMatch(/145/);
  });

  it('guard: changing another line keeps 752 extra row', async () => {
    await renderDialog({}, 'pso-417636');
    await sheet();
    typeQty(480, 1, '10');
    await waitFor(() => expect(block(480).textContent).toMatch(/left|over|10/));
    expect(extraRow(752)?.textContent).toMatch(/145/);
  });

  it('after 752 own splits change it shows no extra row', async () => {
    await renderDialog({}, 'pso-417636');
    await sheet();
    typeQty(752, 1, '400');
    await waitFor(() =>
      expect(
        (block(752).querySelector('[data-qty-split="s467"]') as HTMLInputElement).value,
      ).toBe('400'),
    );
    expect(extraRow(752)).toBeNull();
  });
});

describe('AC-G20 review', () => {
  it('+ Split on 752 (new 649 vs 504) makes one row and focuses its qty', async () => {
    getLineSplits.mockResolvedValue(ownerCase());
    await renderDialog({}, 'pso-417636');
    await sheet();
    fireEvent.click(addBtn(752));
    expect(qty(752, 1).value).toBe('504');
    expect(document.activeElement).toBe(qty(752, 1));
  });

  it('changing only 752 split that sits on 608 removes 608 extra row', async () => {
    const p = saved();
    Object.assign(p.lines.find((l) => l.line_id === 'L608')!, {
      extra_qty: 20,
      extra_remark: 'ORDER 20',
    });
    getLineSplits.mockResolvedValue(p);
    await renderDialog({}, 'pso-417636');
    await sheet();
    expect(extraRow(608)?.textContent).toMatch(/20/);
    typeQty(752, 2, '30');
    await waitFor(() =>
      expect(
        (document.querySelector('[data-qty-split="s37"]') as HTMLInputElement).value,
      ).toBe('30'),
    );
    expect(extraRow(608)).toBeNull();
  });
});
