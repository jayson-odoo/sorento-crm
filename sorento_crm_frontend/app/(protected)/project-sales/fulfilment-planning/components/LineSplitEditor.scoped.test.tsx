/**
 * OI-SPLIT-GUIDE F13 / F22: `LineSplitEditor` with `onlyLineIds` (the guide page's scope) draws
 * only the covered lines plus the lines their saved splits sit on, with no search or toggle, and
 * its Save still sends EVERY line of the order. The board's dialog (unscoped) is unchanged
 * (regression pins, via `LineSplitDialog`).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  blockIds,
  remarkIn,
  renderDialog,
  saveButton,
  savedCase,
  sheet,
  typeDate,
  wireSplit,
} from '@/test-mocks/lineSplitSheetKit';
import { LineSplitEditor } from './LineSplitEditor';

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

beforeEach(() => {
  vi.clearAllMocks();
  getLineSplits.mockResolvedValue(structuredClone(savedCase()));
  saveLineSplits.mockResolvedValue(structuredClone(savedCase()));
});

/** The editor as the guide hosts it: scoped, with a header that offers Save and the search slot. */
function renderEditor(ids?: string[]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LineSplitEditor
        psoId="pso-417636"
        active
        onlyLineIds={ids ? new Set(ids) : undefined}
        renderHeader={(c) => (
          <div>
            <span data-testid="search-slot">{c.searchControls ? 'has-search' : 'no-search'}</span>
            <button type="button" disabled={!c.canSave} onClick={c.save}>
              Save
            </button>
          </div>
        )}
      />
    </QueryClientProvider>,
  );
}

describe('F13: the scoped editor', () => {
  it('lists only the covered line and the line its saved split sits on, never the rest of the order', async () => {
    renderEditor(['L480']);
    await sheet();
    expect(blockIds()).toEqual(['split-line-480', 'split-line-608']);
  });

  it('a covered line with no split lists just itself', async () => {
    renderEditor(['L752']);
    await sheet();
    expect(blockIds()).toEqual(['split-line-752']);
  });

  it('draws no search box and no "Split lines only" toggle, and hands the host no search controls', async () => {
    renderEditor(['L480']);
    await sheet();
    expect(screen.queryByText('Split lines only')).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/item code/i)).not.toBeInTheDocument();
    expect(screen.getByTestId('search-slot')).toHaveTextContent('no-search');
  });
});

describe('F22: Save sends every line, so an edit on a hidden line\'s row is never dropped', () => {
  it('editing the hidden 480\'s 236 split drawn under the shown 608 reaches the PUT body', async () => {
    renderEditor(['L608']);
    await sheet();
    expect(blockIds()).toContain('split-line-608');
    expect(blockIds()).not.toContain('split-line-480');
    // 480's 236 sits on 608: its row is drawn under 608; move its date.
    typeDate(480, 2, '25/11/2026');
    const save = screen.getByRole('button', { name: 'Save' });
    await waitFor(() => expect(save).toBeEnabled());
    fireEvent.click(save);
    await waitFor(() => expect(saveLineSplits).toHaveBeenCalledTimes(1));
    const [, body] = saveLineSplits.mock.calls[0];
    const ids = body.lines.map((l: { line_id: string }) => l.line_id).sort();
    expect(ids).toEqual(['L480', 'L608', 'L752', 'L768', 'L900']);
    const l480 = body.lines.find((l: { line_id: string }) => l.line_id === 'L480');
    expect(l480.splits.map((s: { delivery_date: string }) => s.delivery_date)).toContain('2026-11-25');
  });
});

describe('board dialog pins (unscoped, unchanged)', () => {
  it('lists every line and carries the toggle and the search box', async () => {
    await renderDialog();
    await sheet();
    expect(blockIds()).toHaveLength(5);
    expect(screen.getByText('Split lines only')).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/item code/i)).toBeInTheDocument();
  });

  it('the header counts every line', async () => {
    await renderDialog();
    await sheet();
    expect(screen.getByText(/^5 lines · /)).toBeInTheDocument();
  });

  it('a problem on any line is named by item and qty left, never a line number', async () => {
    const p = structuredClone(savedCase());
    p.lines.find((l) => l.line_id === 'L900')!.splits = [wireSplit('h1', 20, '2026-10-01', 'L900')];
    getLineSplits.mockResolvedValue(p);
    await renderDialog();
    await sheet();
    expect(screen.getByText(/CSK14B: 30 left/)).toBeInTheDocument();
    expect(screen.queryByText(/line 900/)).not.toBeInTheDocument();
  });

  it('F21 (owner ruling): shows no Line column and no "line N" sub-label', async () => {
    await renderDialog();
    const table = await sheet();
    expect(screen.queryByRole('columnheader', { name: /^line$/i })).not.toBeInTheDocument();
    expect(table.textContent).not.toMatch(/\bline \d+/i);
    expect(blockIds()).toContain('split-line-480');
  });
});

describe('F25: every row\'s Remark is an editable box prefilled with the default words (board dialog)', () => {
  const withDefaults = () => {
    const p = structuredClone(savedCase());
    const l480 = p.lines.find((l) => l.line_id === 'L480')!;
    l480.splits = [
      wireSplit('s14', 14, '2026-09-20', 'L480', { remark_generated: 'ADVANCE' }),
      wireSplit('s236', 236, '2026-11-20', 'L608', { remark_generated: 'DELAY' }),
      wireSplit('s167', 167, '2029-11-20', null, { remark_generated: 'DELAY' }),
    ];
    return p;
  };

  it('a split row\'s Remark VALUE is its default words', async () => {
    getLineSplits.mockResolvedValue(withDefaults());
    await renderDialog();
    await sheet();
    expect(remarkIn(480, 2).value).toBe('DELAY');
    expect(remarkIn(480, 1).value).toBe('ADVANCE');
  });

  it('editing shows an "edited" marker; clearing restores the default and removes it', async () => {
    getLineSplits.mockResolvedValue(withDefaults());
    await renderDialog();
    await sheet();
    const cell = () => remarkIn(480, 2).closest('td') as HTMLElement;
    expect(cell().textContent).not.toMatch(/edited/);
    fireEvent.change(remarkIn(480, 2), { target: { value: 'SITE HOLD' } });
    expect(remarkIn(480, 2).value).toBe('SITE HOLD');
    expect(cell().textContent).toMatch(/edited/);
    fireEvent.change(remarkIn(480, 2), { target: { value: '' } });
    await waitFor(() => expect(remarkIn(480, 2).value).toBe('DELAY'));
    expect(cell().textContent).not.toMatch(/edited/);
  });

  it('clearing: backspacing to empty keeps the box EMPTY while focused; the default returns on blur and the marker goes', async () => {
    getLineSplits.mockResolvedValue(withDefaults());
    await renderDialog();
    await sheet();
    const cell = () => remarkIn(480, 2).closest('td') as HTMLElement;
    act(() => remarkIn(480, 2).focus());
    fireEvent.change(remarkIn(480, 2), { target: { value: 'SITE HOLD' } });
    fireEvent.change(remarkIn(480, 2), { target: { value: '' } });
    // still focused: a planner can type fresh text, so the box is NOT refilled with the default
    expect(remarkIn(480, 2).value).toBe('');
    fireEvent.change(remarkIn(480, 2), { target: { value: 'N' } });
    expect(remarkIn(480, 2).value).toBe('N');
    fireEvent.change(remarkIn(480, 2), { target: { value: '' } });
    expect(remarkIn(480, 2).value).toBe('');
    act(() => remarkIn(480, 2).blur());
    await waitFor(() => expect(remarkIn(480, 2).value).toBe('DELAY'));
    expect(cell().textContent).not.toMatch(/edited/);
  });

  it('typing exactly the default text back shows no edited marker and stores nothing', async () => {
    getLineSplits.mockResolvedValue(withDefaults());
    await renderDialog();
    await sheet();
    const cell = () => remarkIn(480, 2).closest('td') as HTMLElement;
    fireEvent.change(remarkIn(480, 2), { target: { value: 'SITE HOLD' } });
    expect(cell().textContent).toMatch(/edited/);
    fireEvent.change(remarkIn(480, 2), { target: { value: 'DELAY' } });
    expect(cell().textContent).not.toMatch(/edited/);
    typeDate(480, 3, '21/11/2029'); // a real edit so Save is on
    const save = saveButton();
    await waitFor(() => expect(save).toBeEnabled());
    fireEvent.click(save);
    await waitFor(() => expect(saveLineSplits).toHaveBeenCalledTimes(1));
    const l480 = saveLineSplits.mock.calls[0][1].lines.find((l: { line_id: string }) => l.line_id === 'L480');
    expect(l480.splits.map((s: { remark: string }) => s.remark ?? '')).toEqual(['', '', '']);
  });

  it('the remark box caps at 500 characters (the API limit)', async () => {
    getLineSplits.mockResolvedValue(withDefaults());
    await renderDialog();
    await sheet();
    expect(remarkIn(480, 2).getAttribute('maxlength')).toBe('500');
  });

  it('the remark box grows with its content: more lines, more rows (not CSS field-sizing alone)', async () => {
    getLineSplits.mockResolvedValue(withDefaults());
    await renderDialog();
    await sheet();
    const rows = () => Number(remarkIn(480, 2).getAttribute('rows') ?? '1');
    expect(rows()).toBe(1);
    fireEvent.change(remarkIn(480, 2), { target: { value: 'one\ntwo\nthree\nfour' } });
    expect(rows()).toBeGreaterThanOrEqual(4);
    fireEvent.change(remarkIn(480, 2), { target: { value: 'short' } });
    expect(rows()).toBe(1);
  });

  it('saving an untouched default stores nothing: the body carries an empty remark', async () => {
    getLineSplits.mockResolvedValue(withDefaults());
    await renderDialog();
    await sheet();
    typeDate(480, 3, '21/11/2029'); // a real edit so Save is on; the remarks stay default
    const save = saveButton();
    await waitFor(() => expect(save).toBeEnabled());
    fireEvent.click(save);
    await waitFor(() => expect(saveLineSplits).toHaveBeenCalledTimes(1));
    const l480 = saveLineSplits.mock.calls[0][1].lines.find((l: { line_id: string }) => l.line_id === 'L480');
    expect(l480.splits.map((s: { remark: string }) => s.remark ?? '')).toEqual(['', '', '']);
  });
});

describe('F29: the Remark cell wraps, it never truncates', () => {
  it('no truncating element inside any Remark cell of the editor', async () => {
    await renderDialog();
    await sheet();
    const table = screen.getByRole('table', { name: 'Split delivery sheet' });
    const index = Array.from(table.querySelectorAll('thead th')).findIndex(
      (th) => (th.textContent ?? '').trim().toLowerCase() === 'remark',
    );
    expect(index).toBeGreaterThan(-1);
    const cells = Array.from(table.querySelectorAll('tbody tr')).map((tr) => (tr as HTMLTableRowElement).cells[index]);
    for (const td of cells.filter(Boolean)) {
      expect(td.querySelector('.truncate'), 'remark cell must wrap').toBeNull();
      expect(td.className).not.toMatch(/\btruncate\b/);
    }
  });
});
