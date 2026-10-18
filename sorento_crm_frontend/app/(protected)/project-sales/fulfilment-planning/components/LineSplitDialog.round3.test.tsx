/**
 * OI-LINE-SPLIT build round 3 (AC-G1, AC-G2 variant B, AC-G3, AC-G5): the owner's case after
 * Confirm. Customer is a placeholder.
 */
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  block,
  renderDialog,
  sheet,
  wireLine,
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

function afterConfirm() {
  return {
    pso_id: 'pso-417636',
    so_number: 'SO417636',
    so_date: '2026-09-03',
    customer: 'PLACEHOLDER CUSTOMER',
    project: 'PLACEHOLDER PROJECT',
    confirmed_at: '2026-10-18T09:00:00Z',
    lines: [
      wireLine(480, 'CSK14B', 417, '2026-10-20', {
        now_qty: 14, now_date: '2026-09-20', new_qty: 14, new_date: '2026-09-20',
        split_state: 'applied',
        splits: [
          wireSplit('s14', 14, '2026-09-20', 'L480', { remark_generated: 'Advanced to 20/09/2026' }),
          wireSplit('s236', 236, '2026-11-20', 'L608', { remark_generated: 'Delayed to 20/11/2026' }),
          wireSplit('s167', 167, '2029-11-20', 'L608', { remark_generated: 'Delayed to 20/11/2029' }),
        ],
      }),
      wireLine(608, 'CSK14B', 192, '2026-11-20', { now_qty: 632, new_qty: 632 }),
      wireLine(752, 'CSK14B', 504, '2026-12-20', {
        now_qty: 649, now_date: '2027-01-02', new_qty: 649, new_date: '2027-01-02',
        split_state: 'applied',
        extra_qty: 182,
        extra_remark: 'ORDER 182',
        splits: [
          wireSplit('s37', 37, '2026-11-20', 'L608', { remark_generated: 'Advanced to 20/11/2026' }),
          wireSplit('s467', 467, '2027-01-02', 'L752', { remark_generated: 'Delayed to 02/01/2027' }),
        ],
      }),
    ],
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  getLineSplits.mockResolvedValue(afterConfirm());
});

const splitIds = (no: number) =>
  Array.from(block(no).querySelectorAll('tr[data-split-id]')).map((r) =>
    r.getAttribute('data-split-id'),
  );
const row = (id: string) => document.querySelector(`tr[data-split-id="${id}"]`) as HTMLElement;
/** Text of a row: cell text plus every input value. */
const rowText = (tr: Element) =>
  [
    tr.textContent ?? '',
    ...Array.from(tr.querySelectorAll('input')).map((i) => i.value),
  ].join(' ');
const hasLineCell = (tr: Element, no: number) =>
  new RegExp(`(^|\\D)${no}(\\D|$)`).test(tr.textContent ?? '');

describe('AC-G1 refer back status', () => {
  it('the status line says Confirmed 18/10/2026 once, no per-line Confirmed', async () => {
    await renderDialog({}, 'pso-417636');
    await sheet();
    const status = screen.getByRole('status', { name: 'Split status' });
    expect(status.textContent).toMatch(/Confirmed 18\/10\/2026/);
    const all = document.body.textContent ?? '';
    expect((all.match(/Confirmed/g) ?? []).length).toBe(1);
  });
});

describe('AC-G2 variant B: a split shows in the block of the line it sits on', () => {
  it('236 and 167 sit in 608 with LINE 480; 37 sits in 608 with LINE 752', async () => {
    await renderDialog({}, 'pso-417636');
    await sheet();
    const b608 = block(608);
    for (const [id, own] of [['s236', 480], ['s167', 480], ['s37', 752]] as const) {
      expect(b608.contains(row(id)), `${id} in block 608`).toBe(true);
      expect(hasLineCell(row(id), own), `${id} LINE ${own}`).toBe(true);
    }
  });

  it('480 holds only the 14 row, 752 holds only the 467 row plus the extra row', async () => {
    await renderDialog({}, 'pso-417636');
    await sheet();
    expect(splitIds(480)).toEqual(['s14']);
    expect(splitIds(752)).toEqual(['s467']);
  });
});

describe('AC-G3 extra row', () => {
  it('752 shows 182 at 02/01/2027, not editable, remark ORDER 182', async () => {
    await renderDialog({}, 'pso-417636');
    await sheet();
    const rows = Array.from(block(752).querySelectorAll('tr'));
    const extra = rows.find((tr) => !tr.hasAttribute('data-split-id') && /182/.test(rowText(tr)));
    expect(extra, 'an extra row with 182').toBeTruthy();
    const text = rowText(extra!);
    expect(text).toMatch(/02\/01\/2027/);
    expect(text).toMatch(/ORDER 182/);
    expect(within(extra!).queryByLabelText(/^Quantity, line/)).toBeNull();
    const qtyInputs = Array.from(extra!.querySelectorAll('input')).filter((i) => i.value === '182');
    expect(qtyInputs.filter((i) => !i.readOnly && !i.disabled)).toHaveLength(0);
  });
});

describe('AC-G5 remark pre-fill', () => {
  const remarkCell = () => row('s236').querySelector('[data-nav-col="remark"]') as HTMLInputElement;
  const shown = (el: HTMLInputElement) =>
    `${el.textContent ?? ''} ${el.value ?? ''} ${el.getAttribute('placeholder') ?? ''}`;

  it('an empty stored remark shows remark_generated, marked muted', async () => {
    await renderDialog({}, 'pso-417636');
    await sheet();
    const cell = row('s236').querySelector('[data-remark-generated="true"]') as HTMLElement;
    expect(cell, 'muted generated remark marker').toBeTruthy();
    expect(rowText(row('s236'))).toMatch(/Delayed to 20\/11\/2026/);
    expect(
      (cell.textContent ?? '') + ((cell as HTMLInputElement).value ?? '') + (cell.getAttribute('placeholder') ?? ''),
    ).toMatch(/Delayed to 20\/11\/2026/);
  });

  it('typing replaces it, clearing restores it', async () => {
    await renderDialog({}, 'pso-417636');
    await sheet();
    fireEvent.change(remarkCell(), { target: { value: 'Site hold' } });
    await waitFor(() => expect(shown(remarkCell())).toMatch(/Site hold/));
    expect(row('s236').querySelector('[data-remark-generated="true"]')).toBeNull();
    expect(rowText(row('s236'))).not.toMatch(/Delayed to 20\/11\/2026/);
    fireEvent.change(remarkCell(), { target: { value: '' } });
    await waitFor(() =>
      expect(row('s236').querySelector('[data-remark-generated="true"]')).toBeTruthy(),
    );
    expect(rowText(row('s236'))).toMatch(/Delayed to 20\/11\/2026/);
  });
});

describe('no equations or labels', () => {
  it('no "->", "=", "not linked", "this line" in the sheet', async () => {
    await renderDialog({}, 'pso-417636');
    const table = await sheet();
    const text = rowText(table) + (screen.getByRole('status', { name: 'Split status' }).textContent ?? '');
    expect(text).not.toMatch(/->|=|not linked|this line/i);
  });
});
