/**
 * OI-SPLIT-VIEW (UAC B1, B8, D1, E): the shared "Split N" chip + (i) popup and the whole-order
 * popup. Round 4 (UAC E): the popup BODY is the split delivery edit sheet read-only
 * (`LineSplitSheet readOnly`), fed by the `LineSplitService.read` payload the pages pass as
 * `payload` (the chip still reads `view`). The line popup shows the block of `lineNo` (and
 * splits moved onto it); the whole-order popup shows every line with saved splits.
 */
import React from 'react';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { LineSplitInfo, OrderSplitsDialog } from './LineSplitInfo';
import type { LineSplitView } from '../types/orderInquiry.types';
import { ownerSavedCase, receivingCase } from '@/test-mocks/lineSplitSheetKit';

const row = (over: Record<string, unknown>) => ({
  qty: '14',
  delivery_date: '2026-09-20',
  change: 'ADVANCE',
  sits_on: 'own',
  sits_on_line_no: 480,
  remark: '',
  is_cancel: false,
  changed: false,
  was_qty: null,
  was_date: null,
  ...over,
});

const VIEW_480: LineSplitView = {
  status: 'confirmed',
  revision_no: 3,
  confirmed_on: '2026-10-19',
  base_qty: '417',
  base_date: '2026-10-20',
  now_qty: '14',
  now_date: '2026-09-20',
  total_qty: '417',
  rows: [
    row({}),
    row({ qty: '236', delivery_date: '2026-11-20', change: 'DELAY', sits_on: 'new', sits_on_line_no: null }),
    row({ qty: '167', delivery_date: '2026-11-20', change: 'DELAY', sits_on: 'new', sits_on_line_no: null }),
  ],
} as unknown as LineSplitView;

const VIEW_480_SAVED: LineSplitView = {
  ...VIEW_480,
  status: 'saved',
  revision_no: null,
  confirmed_on: null,
  rows: [
    row({}),
    row({ qty: '236', delivery_date: '2026-11-20', change: 'DELAY', sits_on: 'new', sits_on_line_no: null }),
    row({
      qty: '167', delivery_date: '2029-11-20', change: 'DELAY', sits_on: 'new', sits_on_line_no: null,
      changed: true, was_date: '2026-11-20',
    }),
  ],
} as unknown as LineSplitView;

const VIEW_752: LineSplitView = {
  status: 'autocount_changed',
  revision_no: null,
  confirmed_on: null,
  base_qty: '504',
  base_date: '2026-12-20',
  now_qty: '649',
  now_date: '2027-01-02',
  total_qty: '649',
  rows: [
    row({ qty: '37', delivery_date: '2026-11-20', change: 'ADVANCE', sits_on: 'own', sits_on_line_no: 752 }),
    row({ qty: '467', delivery_date: '2027-01-02', change: 'DELAY', sits_on: 'new', sits_on_line_no: null }),
    row({ qty: '145', delivery_date: '2027-01-02', change: 'ORDER 145', sits_on: 'extra', sits_on_line_no: 752 }),
  ],
} as unknown as LineSplitView;

beforeEach(() => cleanup());

function info(view: LineSplitView | null, over: Record<string, unknown> = {}) {
  return render(
    <LineSplitInfo
      lineNo={480}
      itemCode="CSK14B"
      soNumber="SO417636"
      view={view}
      {...(over as object)}
    />,
  );
}

describe('LineSplitInfo - the chip and the (i) button', () => {
  it('renders nothing for a line without splits', () => {
    const { container } = info(null);
    expect(container).toBeEmptyDOMElement();
  });

  it('reads "Split 3" (the AutoCount extra row is not counted) and offers the (i) button', () => {
    const { unmount } = info(VIEW_480);
    expect(screen.getByText('Split 3')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Show the splits of line 480' })).toBeInTheDocument();
    unmount();
    info(VIEW_752, { lineNo: 752 });
    expect(screen.getByText('Split 2')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Show the splits of line 752' })).toBeInTheDocument();
  });

  it('opens nothing by default', () => {
    info(VIEW_480);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});

describe('LineSplitInfo - the popup is the read-only split sheet (E)', () => {
  function open(payload: unknown, over: Record<string, unknown> = {}) {
    info(VIEW_480, { payload, ...over });
    const button = screen.getByRole('button', { name: `Show the splits of line ${over.lineNo ?? 480}` });
    button.focus();
    fireEvent.click(button);
    return { button, dialog: screen.getByRole('dialog') };
  }
  const ids = (dialog: HTMLElement) =>
    within(dialog).getAllByTestId(/^split-line-/).map((el) => el.getAttribute('data-testid'));

  it('is titled "Line 480 CSK14B: split" with the SO number and the OI line under it', () => {
    const { dialog } = open(ownerSavedCase(), { oiNumber: 'OI-2609-0578' });
    expect(within(dialog).getByText('Line 480 CSK14B: split')).toBeInTheDocument();
    expect(dialog.textContent).toContain('SO417636');
    expect(dialog.textContent).toContain('OI-2609-0578 line 480');
  });

  it('renders the sheet for that one line only: one block, line 480', () => {
    const { dialog } = open(ownerSavedCase());
    expect(within(dialog).getByRole('table', { name: 'Split delivery sheet' })).toBeInTheDocument();
    expect(ids(dialog)).toEqual(['split-line-480']);
  });

  it('shows the change words in the REMARK column and the same column headers as the edit sheet', () => {
    const { dialog } = open(ownerSavedCase());
    const heads = Array.from(dialog.querySelectorAll('thead th')).map((th) => (th.textContent ?? '').trim());
    expect(heads).toContain('Change quantity');
    expect(heads).toContain('New date');
    expect(heads).not.toContain('Balance');
    expect(within(dialog).getByText('ADVANCE')).toBeInTheDocument();
    expect(within(dialog).getAllByText('DELAY')).toHaveLength(2);
  });

  it('reads "Confirmed 19/10/2026" for an applied plan and no "Saved, not confirmed" badge', () => {
    const { dialog } = open(ownerSavedCase());
    expect(dialog.textContent).toContain('Confirmed 19/10/2026');
    expect(within(dialog).queryByText('Saved, not confirmed')).not.toBeInTheDocument();
  });

  it('shows one "Saved, not confirmed" badge when the line is split-edited', () => {
    const { dialog } = open(ownerSavedCase({ edited: true }));
    expect(within(dialog).getAllByText('Saved, not confirmed')).toHaveLength(1);
  });

  it('has no Total text, no note under a REMARK word, no "was", no DataGrid of the old popup', () => {
    const { dialog } = open(ownerSavedCase({ edited: true }));
    const text = dialog.textContent ?? '';
    expect(text).not.toMatch(/Total \d/);
    expect(text).not.toContain('AutoCount 417 @');
    expect(text).not.toContain('New line (not in AutoCount yet)');
    expect(within(dialog).queryByText(/^was /)).not.toBeInTheDocument();
    expect(dialog.querySelectorAll('[data-slot="data-grid-table"]')).toHaveLength(0);
  });

  it('has no input, no grip, no "+ Split", no Save in the popup', () => {
    const { dialog } = open(ownerSavedCase());
    expect(dialog.querySelectorAll('input, textarea, select')).toHaveLength(0);
    expect(dialog.querySelectorAll('[data-drag-handle]')).toHaveLength(0);
    expect(within(dialog).queryByRole('button', { name: /Add a split|Remove split|^Save$/ })).not.toBeInTheDocument();
  });

  it('draws a split that moved onto line 608 under 608 when the popup is opened for 608', () => {
    const { dialog } = open(receivingCase(), { lineNo: 608 });
    expect(ids(dialog)).toContain('split-line-608');
    expect(dialog.textContent).toContain('236');
  });

  it('Escape closes it and returns focus to the (i) button', () => {
    const { button, dialog } = open(ownerSavedCase());
    fireEvent.keyDown(dialog, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(document.activeElement).toBe(button);
  });

  it('Close returns focus to the (i) button too', () => {
    const { button, dialog } = open(ownerSavedCase());
    fireEvent.click(within(dialog).getAllByRole('button', { name: 'Close' })[0]);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(document.activeElement).toBe(button);
  });
});

describe('OrderSplitsDialog - the whole order is the read-only split sheet (E3, E4)', () => {
  function dlg(payload: unknown, over: Record<string, unknown> = {}) {
    render(
      <OrderSplitsDialog
        title="SO417636: splits"
        payload={payload as never}
        open
        onOpenChange={() => {}}
        {...(over as object)}
      />,
    );
    return screen.getByRole('dialog');
  }
  const ids = (dialog: HTMLElement) =>
    within(dialog).getAllByTestId(/^split-line-/).map((el) => el.getAttribute('data-testid'));

  it('lists only the lines with saved splits: 480 and 752, not 608 or 768', () => {
    const dialog = dlg(ownerSavedCase());
    expect(ids(dialog)).toEqual(['split-line-480', 'split-line-752']);
    expect(dialog.textContent).toContain('2 split lines');
  });

  it('shows the AutoCount extra row ORDER 145 and the words in the one sheet', () => {
    const dialog = dlg(ownerSavedCase());
    expect(within(dialog).getAllByRole('table', { name: 'Split delivery sheet' })).toHaveLength(1);
    expect(within(dialog).getByText('ORDER 145')).toBeInTheDocument();
  });

  it('lists a line that only receives a moved split, with that split under it', () => {
    const dialog = dlg(receivingCase());
    expect(ids(dialog)).toEqual(['split-line-480', 'split-line-608', 'split-line-752']);
    expect(within(screen.getByTestId('split-line-608')).getByText('DELAY')).toBeInTheDocument();
  });

  it('reads "1 split line" for one split line', () => {
    const p = ownerSavedCase();
    p.lines[2].splits = [];
    p.lines[2].extra_qty = null;
    const text = dlg(p).textContent ?? '';
    expect(text).toMatch(/1 split line(?!s)/);
    expect(text).not.toContain('1 split lines');
  });

  it('puts the subtitle under the title and "Confirmed 19/10/2026" in the header', () => {
    const dialog = dlg(ownerSavedCase(), { title: 'OI-2609-0578: splits', subtitle: 'SO417636' });
    expect(dialog.textContent).toContain('SO417636');
    expect(dialog.textContent).toContain('Confirmed 19/10/2026');
  });

  it('shows one "Saved, not confirmed" badge when any listed line is split-edited, none otherwise', () => {
    expect(within(dlg(ownerSavedCase({ edited: true }))).getAllByText('Saved, not confirmed')).toHaveLength(1);
    cleanup();
    expect(within(dlg(ownerSavedCase())).queryByText('Saved, not confirmed')).not.toBeInTheDocument();
  });

  it('has no Total text, no per-line headings with badges, no input or grip', () => {
    const dialog = dlg(ownerSavedCase({ edited: true }));
    expect(dialog.textContent).not.toMatch(/Total \d/);
    expect(dialog.textContent).not.toContain('AutoCount 417 @');
    expect(dialog.querySelectorAll('input, textarea, select, [data-drag-handle]')).toHaveLength(0);
    expect(dialog.querySelectorAll('[data-slot="data-grid-table"]')).toHaveLength(0);
  });

  it('shows the empty state when no line is split', () => {
    const p = ownerSavedCase();
    p.lines.forEach((l) => { l.splits = []; l.extra_qty = null; });
    const dialog = dlg(p);
    expect(within(dialog).getByText('No split lines')).toBeInTheDocument();
    expect(within(dialog).getByText('Every line ships as AutoCount has it.')).toBeInTheDocument();
  });

  it('renders nothing while closed', () => {
    render(<OrderSplitsDialog title="SO417636: splits" payload={ownerSavedCase() as never} open={false} onOpenChange={() => {}} />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
