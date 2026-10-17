/**
 * OI-LINE-SPLIT v4 crew audit (17 Oct): a line's PLANNED date (UAC A7, A9) and the pick toast.
 */
import { act, fireEvent, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  addBtn,
  dateIn,
  onSel,
  ownerCase,
  qty,
  queryQty,
  remainQty,
  renderDialog,
  savedCase,
  sheet,
  splitLine,
  toastCalls,
  typeDate,
  typeQty,
  wireSplit,
} from '@/test-mocks/lineSplitSheetKit';

const { getLineSplits, saveLineSplits, toastFn, toastError, toastSuccess, toastWarning } =
  vi.hoisted(() => ({
    getLineSplits: vi.fn(), saveLineSplits: vi.fn(), toastFn: vi.fn(),
    toastError: vi.fn(), toastSuccess: vi.fn(), toastWarning: vi.fn(),
  }));
vi.mock('@/app/(protected)/project-sales/_shared/services/lineSplitService', () => ({
  getLineSplits: (...a: unknown[]) => getLineSplits(...a),
  saveLineSplits: (...a: unknown[]) => saveLineSplits(...a),
}));
vi.mock('@/lib/toast', () => ({
  toast: Object.assign(toastFn, { error: toastError, success: toastSuccess, warning: toastWarning }),
}));

const focused = () => (document.activeElement ?? document.body) as HTMLElement;
const press = (key: string, code: string = key) => fireEvent.keyDown(focused(), { key, code });
async function pickUp(handle: HTMLElement) {
  act(() => handle.focus());
  fireEvent.keyDown(handle, { key: ' ', code: 'Space' });
  await waitFor(() => expect(screen.getByTestId('drop-cancel')).toBeInTheDocument());
}
async function dropIt() {
  press(' ', 'Space');
  await waitFor(() => expect(screen.queryByTestId('drop-cancel')).toBeNull());
}
const toasts = () => toastCalls(toastFn, toastSuccess, toastWarning);
const options = async () => screen.findAllByRole('option');
const pick = (label: RegExp | string) => {
  const o = screen.getAllByRole('option').find((x) => {
    const t = (x.textContent ?? '').trim();
    return typeof label === 'string' ? t === label : label.test(t);
  });
  expect(o, `option ${String(label)}`).toBeDefined();
  fireEvent.click(o!);
};

/** Line 752 split so that 14 stays on it @ 20/09/2026 (the rest cancelled): planned 20/09/2026. */
function with752Split() {
  const p = ownerCase();
  p.lines.find((l) => l.line_id === 'L752')!.splits = [
    wireSplit('k', 14, '2026-09-20', 'L752'),
    wireSplit('c', 490, null, 'L752', { is_cancel: true }),
  ];
  return p;
}

beforeEach(() => {
  vi.clearAllMocks();
  getLineSplits.mockResolvedValue(with752Split());
});

describe('planned date of a line', () => {
  it('dropping a line onto 752 lands on 20/09/2026 and the overlay reads it', async () => {
    await renderDialog();
    await sheet();
    await pickUp(screen.getByRole('button', { name: 'Drag line 480' }));
    press('ArrowDown');
    press('ArrowDown'); // 608, 752
    await waitFor(() =>
      expect(document.body.textContent).toMatch(/→\s*20\/09\/2026 · line 752/),
    );
    await dropIt();
    expect(dateIn(480, 1).value).toBe('20/09/2026');
    expect(onSel(480, 1)).toHaveTextContent(/Line 752/);
  });

  it('the "N left" chip dropped onto 752 lands on 20/09/2026 too', async () => {
    await renderDialog();
    await sheet();
    await splitLine(480);
    typeQty(480, 1, '14');
    await pickUp(screen.getByRole('button', { name: 'Drag the 403 left of line 480' }));
    press('ArrowDown');
    press('ArrowDown');
    await dropIt();
    expect(dateIn(480, 2).value).toBe('20/09/2026');
  });

  it('the AUTOCOUNT LINE option reads "Line 752 · 20/09/2026" and picking it takes that date', async () => {
    await renderDialog();
    await sheet();
    await splitLine(480);
    typeQty(480, 1, '14');
    fireEvent.click(addBtn(480));
    fireEvent.click(onSel(480, 2));
    await options();
    expect(screen.getAllByRole('option').map((o) => (o.textContent ?? '').trim())).toContain(
      'Line 752 · 20/09/2026',
    );
    pick('Line 752 · 20/09/2026');
    await waitFor(() => expect(dateIn(480, 2).value).toBe('20/09/2026'));
  });

  it('a typed date stays as typed', async () => {
    await renderDialog();
    await sheet();
    await splitLine(480);
    typeQty(480, 1, '14');
    fireEvent.click(addBtn(480));
    fireEvent.click(onSel(480, 2));
    await options();
    pick('Line 752 · 20/09/2026');
    await waitFor(() => expect(dateIn(480, 2).value).toBe('20/09/2026'));
    typeDate(480, 2, '05/10/2026');
    expect(dateIn(480, 2).value).toBe('05/10/2026');
  });
});

describe('picking another line shows the drop toast', () => {
  async function openPick(no: number, n: number) {
    fireEvent.click(onSel(no, n));
    await options();
  }
  const moved = (re: RegExp) => toasts().find((t) => re.test(t.msg));

  it('"Moved 403 to 20/11/2026 · line 608" with Undo, and Undo restores the row', async () => {
    getLineSplits.mockResolvedValue(ownerCase());
    await renderDialog();
    await sheet();
    await splitLine(480);
    typeQty(480, 1, '14');
    fireEvent.click(addBtn(480));
    await openPick(480, 2);
    pick(/^Line 608/);
    await waitFor(() => expect(dateIn(480, 2).value).toBe('20/11/2026'));
    const t = moved(/^Moved 403 to 20\/11\/2026 · line 608/);
    expect(t, 'pick toast').toBeDefined();
    expect(t!.opts?.action?.label).toBe('Undo');
    act(() => t!.opts!.action!.onClick());
    await waitFor(() => expect(dateIn(480, 2).value).toBe('20/10/2026'));
    expect(onSel(480, 2)).toHaveTextContent(/New line/);
    expect(qty(480, 2).value).toBe('403');
  });

  it('when the pick merges the toast shows and Undo brings both rows back', async () => {
    const p = savedCase();
    p.lines.find((l) => l.line_id === 'L480')!.splits = [
      wireSplit('a', 14, '2026-09-20', 'L480'),
      wireSplit('b', 236, '2026-11-20', 'L608', { remark: 'first' }),
      wireSplit('c', 167, '2029-11-20', null, { remark: 'second' }),
    ];
    getLineSplits.mockResolvedValue(p);
    await renderDialog();
    await sheet();
    await openPick(480, 3);
    pick(/^Line 608/);
    await waitFor(() => expect(queryQty(480, 3)).toBeNull());
    expect(qty(480, 2).value).toBe('403');
    const t = moved(/^Moved 167 to 20\/11\/2026 · line 608/);
    expect(t, 'pick toast on a merge').toBeDefined();
    act(() => t!.opts!.action!.onClick());
    await waitFor(() => expect(qty(480, 3).value).toBe('167'));
    expect(qty(480, 2).value).toBe('236');
    expect(screen.getByLabelText('Remark, line 480 split 2')).toHaveValue('first');
    expect(screen.getByLabelText('Remark, line 480 split 3')).toHaveValue('second');
    expect(dateIn(480, 3).value).toBe('20/11/2029');
  });

  it('picking New line, Cancel or this line shows no Moved toast', async () => {
    getLineSplits.mockResolvedValue(ownerCase());
    await renderDialog();
    await sheet();
    await splitLine(480);
    typeQty(480, 1, '14');
    fireEvent.click(addBtn(480));
    await openPick(480, 2);
    pick('Cancel');
    await waitFor(() => expect(screen.queryByLabelText('Date, line 480 split 2')).toBeNull());
    await openPick(480, 2);
    pick('Line 480 (this line)');
    await waitFor(() => expect(dateIn(480, 2).value).toBe('20/10/2026'));
    expect(toasts().filter((t) => /^Moved/.test(t.msg))).toHaveLength(0);
    void remainQty;
  });
});
