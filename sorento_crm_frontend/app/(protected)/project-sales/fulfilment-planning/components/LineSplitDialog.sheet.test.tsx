/**
 * OI-LINE-SPLIT v4: the one split sheet (UAC A2 to A7, A10 to A12), through the dialog.
 * DOM contract: PLAN-oi-line-split-16oct.md "Build v4". Drag is in LineSplitDialog.drag.test.tsx.
 */
import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  addBtn,
  addedCase,
  balance,
  block,
  blockIds,
  dateIn,
  leaveSheet,
  ownerCase,
  qty,
  queryQty,
  remainDate,
  remainQty,
  remarkIn,
  removeBtn,
  renderDialog,
  savedCase,
  sheet,
  splitLine,
  typeDate,
  typeQty,
} from '@/test-mocks/lineSplitSheetKit';

const { getLineSplits, saveLineSplits, toastFn, toastError, toastSuccess, toastWarning } =
  vi.hoisted(() => ({
    getLineSplits: vi.fn(),
    saveLineSplits: vi.fn(),
    toastFn: vi.fn(),
    toastError: vi.fn(),
    toastSuccess: vi.fn(),
    toastWarning: vi.fn(),
  }));
vi.mock('@/app/(protected)/project-sales/_shared/services/lineSplitService', () => ({
  getLineSplits: (...a: unknown[]) => getLineSplits(...a),
  saveLineSplits: (...a: unknown[]) => saveLineSplits(...a),
}));
vi.mock('@/lib/toast', () => ({
  toast: Object.assign(toastFn, {
    error: toastError,
    success: toastSuccess,
    warning: toastWarning,
  }),
}));

beforeEach(() => {
  vi.clearAllMocks();
  getLineSplits.mockResolvedValue(structuredClone(ownerCase()));
  saveLineSplits.mockResolvedValue(structuredClone(ownerCase()));
});

describe('AC-A2 one table, columns and line sort', () => {
  it('renders one table with a tbody per line, sorted by item, location, base date, line no', async () => {
    await renderDialog();
    await sheet();
    expect(blockIds()).toEqual([
      'split-line-768',
      'split-line-480',
      'split-line-608',
      'split-line-752',
      'split-line-900',
    ]);
  });

  it('lists the columns in order: LINE ... BALANCE, NEW QTY / NEW DATE beside QTY / DELIVERY DATE, no AUTOCOUNT LINE', async () => {
    await renderDialog();
    const table = await sheet();
    const heads = within(table)
      .getAllByRole('columnheader')
      .map((h) => (h.textContent ?? '').trim().toLowerCase())
      .filter(Boolean);
    expect(heads).toEqual([
      'line',
      'so date',
      's/o no',
      'item code',
      'location',
      'qty',
      'new qty',
      'delivery date',
      'new date',
      'change quantity',
      'change date',
      'remark',
      'balance',
    ]);
  });

  it('shows the base cells of an unsplit line: line no, SO date, S/O no, item, location, qty, date', async () => {
    await renderDialog();
    await sheet();
    const text = block(480).textContent ?? '';
    expect(text).toContain('480');
    expect(text).toContain('03/09/2026');
    expect(text).toContain('SO417636');
    expect(text).toContain('CSK14B');
    expect(text).toContain('BRW-BB');
    expect(text).toContain('417');
    expect(text).toContain('20/10/2026');
  });
});

describe('AC-A3 merged cells and the extra notes', () => {
  it('a split line stacks one row per split and merges its base cells with rowSpan', async () => {
    getLineSplits.mockResolvedValue(savedCase());
    await renderDialog();
    await sheet();
    // Variant B (AC-G2): 480 keeps the splits that stay on it (14) and the one on a new line
    // (167); the 236 dropped on 608 is drawn under 608 with its own LINE cell 480.
    const b = block(480);
    expect(b.querySelectorAll('tr')).toHaveLength(2);
    const itemCell = within(b).getByText('CSK14B').closest('td')!;
    expect(itemCell.getAttribute('rowspan')).toBe('2');
    expect(balance(480).closest('td')!.getAttribute('rowspan')).toBe('2');
    // the merged cells appear once, in the first row
    expect(within(b).getAllByText('CSK14B')).toHaveLength(1);
    // each split row has its own qty input, numbered by its own line
    expect([1, 2, 3].map((n) => qty(480, n).value)).toEqual(['14', '236', '167']);
    expect(dateIn(480, 2).value).toBe('20/11/2026');
    const moved = qty(480, 2).closest('tr') as HTMLTableRowElement;
    expect(block(608).contains(moved), 's236 drawn in block 608').toBe(true);
    expect(b.contains(moved)).toBe(false);
    expect(
      Array.from(moved.cells).some((td) => (td.textContent ?? '').trim() === '480'),
      's236 LINE cell 480',
    ).toBe(true);
  });

  it('an unsplit line has single-row cells (no rowSpan above 1)', async () => {
    await renderDialog();
    await sheet();
    const cells = Array.from(block(608).querySelectorAll('td[rowspan]'));
    for (const c of cells) expect(Number(c.getAttribute('rowspan'))).toBeLessThanOrEqual(1);
  });

  it('a line with a pending change shows NEW QTY and NEW DATE cells, never "AutoCount now"', async () => {
    await renderDialog();
    await sheet();
    expect(block(752).textContent).toContain('649');
    expect(block(752).textContent).toContain('02/01/2027');
    expect(block(752).textContent).not.toMatch(/AutoCount now/);
    expect(block(608).textContent).not.toMatch(/AutoCount now/);
  });

  it('an AutoCount-added line shows QTY 0, NEW QTY and NEW DATE (no "Added in AutoCount" text) and cannot be split or dragged', async () => {
    getLineSplits.mockResolvedValue(addedCase());
    await renderDialog({ focusLineId: 'L16' }, 'pso-424910');
    await sheet();
    const b = block(32);
    expect(b.textContent).not.toMatch(/Added in AutoCount/);
    expect(b.textContent).toContain('16/10/2026');
    expect(within(b).getAllByText('0').length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: 'Split line 32 quantity' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Add a split to line 32' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Drag line 32' })).toBeNull();
  });

  it('a line other lines splits sit on shows "+N from line M" for each', async () => {
    getLineSplits.mockResolvedValue(savedCase());
    await renderDialog();
    await sheet();
    expect(block(608).textContent).toMatch(/\+236 from line 480/);
    expect(block(480).textContent).not.toMatch(/from line 480/);
    // the split with no sits-on line (a new line) is shown on no other line
    expect(block(752).textContent).not.toMatch(/from line/);
  });

  it('"+N from line M" also shows on an added line', async () => {
    getLineSplits.mockResolvedValue(addedCase());
    await renderDialog({ focusLineId: 'L16' }, 'pso-424910');
    await sheet();
    expect(block(32).textContent).toMatch(/\+4 from line 16/);
  });

  it('a line whose saved splits are stale shows the "AutoCount changed" pill; a line that acts shows none', async () => {
    const p = savedCase();
    p.lines.find((l) => l.line_id === 'L480')!.split_state = 'stale';
    p.lines.find((l) => l.line_id === 'L480')!.acting = false;
    getLineSplits.mockResolvedValue(p);
    await renderDialog();
    await sheet();
    expect(within(block(480)).getByText(/AutoCount changed/i)).toBeInTheDocument();
    expect(within(block(608)).queryByText(/AutoCount changed/i)).toBeNull();
  });

  it('an applied line shows no AutoCount changed pill', async () => {
    const q = savedCase();
    q.lines.find((l) => l.line_id === 'L480')!.split_state = 'applied';
    q.lines.find((l) => l.line_id === 'L480')!.acting = false;
    getLineSplits.mockResolvedValue(q);
    await renderDialog();
    await sheet();
    expect(screen.queryByText(/AutoCount changed/i)).toBeNull();
  });
});

describe('AC-A4 REMAIN', () => {
  it('an unsplit line shows its own QTY and DELIVERY DATE in CHANGE QUANTITY and CHANGE DATE, never the word REMAIN', async () => {
    await renderDialog();
    await sheet();
    expect(remainQty(608)).toHaveTextContent('192');
    expect(remainDate(608)).toHaveTextContent('20/11/2026');
    expect(queryQty(608, 1)).toBeNull();
  });

  it('inside Confirm the cells show the BASE values, not AutoCount now', async () => {
    await renderDialog();
    await sheet();
    // line 752: base 504 @ 20/12/2026, AutoCount now 649 @ 02/01/2027
    expect(remainQty(752)).toHaveTextContent('504');
    expect(remainQty(752)).not.toHaveTextContent('649');
    expect(remainDate(752)).toHaveTextContent('20/12/2026');
    expect(remainDate(752)).not.toHaveTextContent('02/01/2027');
  });

  it('the sheet shows no REMAIN text outside a change pill while no line is split', async () => {
    await renderDialog();
    await sheet();
    expect(within(await sheet()).queryByText(/REMAIN/)).toBeNull();
    expect(remainQty(608).textContent).not.toMatch(/REMAIN/);
    expect(remainDate(608).textContent).not.toMatch(/REMAIN/);
  });

  it('a line put back to its base reads its values again, not REMAIN', async () => {
    await renderDialog();
    await sheet();
    await splitLine(480);
    leaveSheet();
    await waitFor(() => expect(remainQty(480)).toHaveTextContent('417'));
    expect(remainDate(480)).toHaveTextContent('20/10/2026');
    expect(within(block(480)).queryByText(/REMAIN/)).toBeNull();
  });

  it('clicking the REMAIN qty cell makes one split row (base qty, base date, this line) focused in qty', async () => {
    await renderDialog();
    await sheet();
    const q = await splitLine(480);
    expect((q as HTMLInputElement).value).toBe('417');
    expect(dateIn(480, 1).value).toBe('20/10/2026');
    expect(document.activeElement).toBe(q);
    expect(screen.queryByRole('button', { name: 'Split line 480 quantity' })).toBeNull();
    // the other lines still show their values
    expect(remainQty(608)).toBeInTheDocument();
  });

  it('clicking the REMAIN date cell puts focus in the date input', async () => {
    await renderDialog();
    await sheet();
    fireEvent.click(remainDate(480));
    const d = await screen.findByLabelText('Date, line 480 split 1');
    expect(document.activeElement).toBe(d);
    expect(qty(480, 1).value).toBe('417');
  });

  it('typing a digit on the REMAIN qty cell splits the line with the digit in qty', async () => {
    await renderDialog();
    await sheet();
    fireEvent.keyDown(remainQty(480), { key: '5' });
    const q = (await screen.findByLabelText('Quantity, line 480 split 1')) as HTMLInputElement;
    expect(document.activeElement).toBe(q);
    expect(q.value).toBe('5');
  });

  it('typing a digit or "/" on the REMAIN date cell splits the line with the key in the date input', async () => {
    await renderDialog();
    await sheet();
    fireEvent.keyDown(remainDate(480), { key: '2' });
    const d = (await screen.findByLabelText('Date, line 480 split 1')) as HTMLInputElement;
    expect(document.activeElement).toBe(d);
    expect(d.value).toContain('2');

    fireEvent.keyDown(remainDate(608), { key: '/' });
    const d2 = (await screen.findByLabelText('Date, line 608 split 1')) as HTMLInputElement;
    expect(document.activeElement).toBe(d2);
    expect(d2.value).toContain('/');
  });

  it('when focus leaves a line whose only split equals its base it reads REMAIN again, remark kept', async () => {
    await renderDialog();
    await sheet();
    await splitLine(480);
    const remark = screen.getByLabelText(/^Remark,? line 480( split 1)?$/);
    act(() => (remark as HTMLElement).focus());
    fireEvent.change(remark, { target: { value: 'hold for site' } });
    leaveSheet();
    await waitFor(() => expect(remainQty(480)).toBeInTheDocument());
    expect(queryQty(480, 1)).toBeNull();
    expect(screen.getByLabelText(/^Remark,? line 480( split 1)?$/)).toHaveValue('hold for site');
  });

  it('a split that differs from its base stays split when focus leaves', async () => {
    await renderDialog();
    await sheet();
    await splitLine(480);
    typeQty(480, 1, '14');
    leaveSheet();
    await new Promise((r) => setTimeout(r, 30));
    expect(qty(480, 1).value).toBe('14');
    expect(screen.queryByRole('button', { name: 'Split line 480 quantity' })).toBeNull();
  });

  it('a zero-qty split is dropped when focus leaves its line', async () => {
    await renderDialog();
    await sheet();
    await splitLine(480);
    fireEvent.click(addBtn(480)); // nothing is left, so the new split is 0
    expect(qty(480, 2).value).toBe('0');
    leaveSheet();
    await waitFor(() => expect(remainQty(480)).toBeInTheDocument());
    expect(queryQty(480, 2)).toBeNull();
  });
});

describe('AC-A5 + Split, Ctrl/Cmd+Enter, remove', () => {
  it('+ Split fills what is left, on the base date, qty focused and selected', async () => {
    await renderDialog();
    await sheet();
    await splitLine(480);
    typeQty(480, 1, '14');
    fireEvent.click(addBtn(480));
    const q2 = qty(480, 2);
    expect(q2.value).toBe('403');
    expect(dateIn(480, 2).value).toBe('20/10/2026');
    expect(document.activeElement).toBe(q2);
    expect((q2.selectionEnd ?? 0) - (q2.selectionStart ?? 0)).toBe(3);
    expect(balance(480).textContent).toMatch(/^\s*0/);
  });

  it('+ Split on an unsplit line makes its own split plus a new one of 0', async () => {
    await renderDialog();
    await sheet();
    fireEvent.click(addBtn(608));
    expect(qty(608, 1).value).toBe('192');
    expect(qty(608, 2).value).toBe('0');
  });

  it('Ctrl+Enter and Cmd+Enter in a split row add a split under the line', async () => {
    await renderDialog();
    await sheet();
    await splitLine(480);
    typeQty(480, 1, '14');
    fireEvent.keyDown(qty(480, 1), { key: 'Enter', ctrlKey: true });
    expect(qty(480, 2).value).toBe('403');
    fireEvent.keyDown(qty(480, 2), { key: 'Enter', metaKey: true });
    expect(qty(480, 3).value).toBe('0');
  });

  it('the x button removes a split row at once, with no confirm', async () => {
    await renderDialog();
    await sheet();
    await splitLine(480);
    typeQty(480, 1, '14');
    fireEvent.click(addBtn(480));
    fireEvent.click(removeBtn(480, 2));
    expect(queryQty(480, 2)).toBeNull();
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(balance(480).textContent).toMatch(/403 left/);
  });

  it('Ctrl+Backspace in a split row removes it', async () => {
    await renderDialog();
    await sheet();
    await splitLine(480);
    typeQty(480, 1, '14');
    fireEvent.click(addBtn(480));
    fireEvent.keyDown(qty(480, 2), { key: 'Backspace', ctrlKey: true });
    expect(queryQty(480, 2)).toBeNull();
  });
});

describe('AC-A6 balance', () => {
  it('shows "N left" as a draggable chip when short, "N over" when over, "0" when it adds up', async () => {
    await renderDialog();
    await sheet();
    await splitLine(480);
    typeQty(480, 1, '14');
    expect(balance(480).textContent).toMatch(/403 left/);
    expect(
      screen.getByRole('button', { name: 'Drag the 403 left of line 480' }),
    ).toBeInTheDocument();

    typeQty(480, 1, '500');
    expect(balance(480).textContent).toMatch(/83 over/);
    expect(screen.queryByRole('button', { name: /^Drag the .* left of line 480$/ })).toBeNull();

    typeQty(480, 1, '417');
    expect(balance(480).textContent).not.toMatch(/left|over/);
    expect(balance(480).textContent).toMatch(/^\s*0/);
  });

  it('a line that is not split shows only "+ Split"', async () => {
    await renderDialog();
    await sheet();
    expect(balance(608).textContent).not.toMatch(/left|over|^\s*0/);
    expect(addBtn(608)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Drag the .* left of line 608/ })).toBeNull();
  });
});

describe('AC-A10 keyboard in the cells', () => {
  async function twoRows() {
    await renderDialog();
    await sheet();
    await splitLine(480);
    typeQty(480, 1, '14');
    fireEvent.click(addBtn(480));
  }

  it('Enter and ArrowDown go to the same column one row down; Shift+Enter and ArrowUp one row up', async () => {
    await twoRows();
    act(() => qty(480, 1).focus());
    fireEvent.keyDown(qty(480, 1), { key: 'Enter' });
    expect(document.activeElement).toBe(qty(480, 2));
    fireEvent.keyDown(qty(480, 2), { key: 'Enter', shiftKey: true });
    expect(document.activeElement).toBe(qty(480, 1));
    fireEvent.keyDown(qty(480, 1), { key: 'ArrowDown' });
    expect(document.activeElement).toBe(qty(480, 2));
    fireEvent.keyDown(qty(480, 2), { key: 'ArrowUp' });
    expect(document.activeElement).toBe(qty(480, 1));
  });

  it('Enter in the remark and date columns stays in that column', async () => {
    await twoRows();
    act(() => dateIn(480, 1).focus());
    fireEvent.keyDown(dateIn(480, 1), { key: 'Enter' });
    expect(document.activeElement).toBe(dateIn(480, 2));
    act(() => remarkIn(480, 1).focus());
    fireEvent.keyDown(remarkIn(480, 1), { key: 'ArrowDown' });
    expect(document.activeElement).toBe(remarkIn(480, 2));
  });

  it('from the last split row, Enter goes down to the next line REMAIN qty cell', async () => {
    await twoRows();
    act(() => qty(480, 2).focus());
    fireEvent.keyDown(qty(480, 2), { key: 'Enter' });
    expect(document.activeElement).toBe(remainQty(608));
  });

  it('Ctrl+Z undoes the last change', async () => {
    await twoRows();
    expect(qty(480, 2)).toBeInTheDocument();
    fireEvent.keyDown(qty(480, 2), { key: 'z', ctrlKey: true });
    await waitFor(() => expect(queryQty(480, 2)).toBeNull());
  });
});

describe('AC-A11 change pill per split against its own line base date', () => {
  it('later DELAY, earlier ADVANCE, same REMAIN, cancel CANCEL', async () => {
    const p = ownerCase();
    p.lines.find((l) => l.line_id === 'L480')!.splits = [
      { id: 'a', qty: 14, delivery_date: '2026-09-20', is_cancel: false, sits_on_line_id: 'L480', remark: '', remark_generated: '' },
      { id: 'b', qty: 100, delivery_date: '2026-10-20', is_cancel: false, sits_on_line_id: 'L480', remark: '', remark_generated: '' },
      { id: 'c', qty: 200, delivery_date: '2026-11-20', is_cancel: false, sits_on_line_id: 'L608', remark: '', remark_generated: '' },
      { id: 'd', qty: 103, delivery_date: null, is_cancel: true, sits_on_line_id: 'L480', remark: '', remark_generated: '' },
    ];
    getLineSplits.mockResolvedValue(p);
    await renderDialog();
    await sheet();
    const row = (n: number) => qty(480, n).closest('tr') as HTMLElement;
    expect(within(row(1)).getByText('ADVANCE')).toBeInTheDocument();
    expect(within(row(2)).getByText('REMAIN')).toBeInTheDocument();
    expect(within(row(3)).getByText('DELAY')).toBeInTheDocument();
    expect(within(row(4)).getAllByText(/^CANCEL/).length).toBeGreaterThan(0);
  });
});

describe('AC-A12 header, search, split-only switch and the status line', () => {
  it('shows "Split delivery" and "<SO no> · <SO date> · <customer>"', async () => {
    await renderDialog();
    await sheet();
    const dialog = await screen.findByTestId('line-split-dialog');
    expect(dialog.textContent).toContain('Split delivery');
    expect(dialog.textContent).toContain(
      'SO417636 · 03/09/2026 · GLOBAL INGRESS SDN BHD (PROJECT)',
    );
    expect(screen.getByRole('button', { name: /^save$/i })).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /^close$/i }).length).toBeGreaterThan(0);
  });

  it('search by item code narrows the lines', async () => {
    await renderDialog();
    await sheet();
    fireEvent.change(screen.getByPlaceholderText(/item code/i), { target: { value: 'CSK11A' } });
    await waitFor(() => expect(blockIds()).toEqual(['split-line-768']));
  });

  it('the "Split lines only" switch shows only split lines', async () => {
    getLineSplits.mockResolvedValue(savedCase());
    await renderDialog();
    await sheet();
    expect(blockIds()).toHaveLength(5);
    fireEvent.click(screen.getByRole('switch', { name: /split lines only/i }));
    await waitFor(() => expect(blockIds()).toEqual(['split-line-480']));
  });

  it('the status line counts lines, products and split lines', async () => {
    getLineSplits.mockResolvedValue(savedCase());
    await renderDialog();
    await sheet();
    expect(screen.getByRole('status', { name: /split status/i }).textContent).toMatch(/5 lines · 2 products · 1 split/);
  });

  it('names each line that does not add up, with Show that clears the filters and focuses the line', async () => {
    await renderDialog();
    await sheet();
    await splitLine(480);
    typeQty(480, 1, '14');
    leaveSheet();
    const status = screen.getByRole('status', { name: /split status/i });
    expect(status.textContent).toMatch(/CSK14B line 480: 403 left/);

    // hide the line, then Show brings it back
    fireEvent.change(screen.getByPlaceholderText(/item code/i), { target: { value: 'CSK11A' } });
    await waitFor(() => expect(blockIds()).toEqual(['split-line-768']));
    fireEvent.click(within(screen.getByRole('status', { name: /split status/i })).getByText(/^Show$/));
    await waitFor(() => expect(blockIds()).toContain('split-line-480'));
    expect(screen.getByPlaceholderText(/item code/i)).toHaveValue('');
    await waitFor(() => expect(block(480).contains(document.activeElement)).toBe(true));
  });

  it('says "N over" and "date to fill" in the status line', async () => {
    await renderDialog();
    await sheet();
    await splitLine(480);
    typeQty(480, 1, '500');
    expect(screen.getByRole('status', { name: /split status/i }).textContent).toMatch(/CSK14B line 480: 83 over/);
    typeQty(480, 1, '417');
    typeDate(480, 1, '');
    await waitFor(() =>
      expect(screen.getByRole('status', { name: /split status/i }).textContent).toMatch(/CSK14B line 480: date to fill/),
    );
  });
});
