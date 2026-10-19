/**
 * OI-SPLIT-VIEW (UAC B1 to B4, B8, D1): the one shared "Split N" chip + (i) popup and the
 * whole-order popup. Red until `LineSplitInfo.tsx` exists. Both pages render this component,
 * so the same fixtures (SO417636, 480 and 752) stand for both.
 */
import React from 'react';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { LineSplitInfo, OrderSplitsDialog } from './LineSplitInfo';
import type { LineSplitView } from '../types/orderInquiry.types';

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

describe('LineSplitInfo - the popup', () => {
  function open(view: LineSplitView, over: Record<string, unknown> = {}) {
    info(view, over);
    const button = screen.getByRole('button', { name: `Show the splits of line ${over.lineNo ?? 480}` });
    button.focus();
    fireEvent.click(button);
    return { button, dialog: screen.getByRole('dialog') };
  }

  it('is titled "Line 480 CSK14B: split" with the SO number and the OI line under it', () => {
    const { dialog } = open(VIEW_480, { oiNumber: 'OI-2609-0578' });
    expect(within(dialog).getByText('Line 480 CSK14B: split')).toBeInTheDocument();
    expect(dialog.textContent).toContain('SO417636');
    expect(dialog.textContent).toContain('OI-2609-0578 line 480');
  });

  it('names the confirmed status with its revision and date', () => {
    const { dialog } = open(VIEW_480);
    expect(within(dialog).getByText('Confirmed')).toBeInTheDocument();
    expect(dialog.textContent).toContain('revision 3, 19/10/2026');
  });

  it('names the saved and the AutoCount changed statuses', () => {
    const { dialog } = open(VIEW_480_SAVED);
    expect(within(dialog).getByText('Saved, not confirmed')).toBeInTheDocument();
    cleanup();
    const second = open(VIEW_752, { lineNo: 752 });
    expect(within(second.dialog).getByText('AutoCount changed')).toBeInTheDocument();
  });

  it('lists the headers, one row per split, the date as dd/mm/yyyy, and where each sits', () => {
    const { dialog } = open(VIEW_480);
    for (const head of ['Qty', 'Delivery date', 'Change', 'Sits on', 'Remark']) {
      expect(within(dialog).getByText(head)).toBeInTheDocument();
    }
    const text = dialog.textContent ?? '';
    expect(text).toContain('20/09/2026');
    expect(text).toContain('ADVANCE');
    expect(text).toContain('line 480');
    expect(text).toContain('New line (not in AutoCount yet)');
    expect(text).toContain('DELAY');
    expect(text).not.toMatch(/\d{4}-\d{2}-\d{2}/); // no ISO dates on screen
  });

  it('ends with the total row: the sum and "AutoCount <base> @ <date>, now <qty> @ <date>"', () => {
    const { dialog } = open(VIEW_480);
    expect(dialog.textContent).toContain('417');
    expect(dialog.textContent).toContain('AutoCount 417 @ 20/10/2026, now 14 @ 20/09/2026');
  });

  it('prints the AutoCount extra row after the splits', () => {
    const { dialog } = open(VIEW_752, { lineNo: 752 });
    expect(dialog.textContent).toContain('ORDER 145');
    expect(dialog.textContent).toContain('line 752 (AutoCount extra)');
    expect(dialog.textContent).toContain('AutoCount 504 @ 20/12/2026, now 649 @ 02/01/2027');
  });

  it('shows "was 20/11/2026" under the one changed date, and nothing else is marked', () => {
    const { dialog } = open(VIEW_480_SAVED);
    expect(within(dialog).getAllByText(/^was /)).toHaveLength(1);
    expect(within(dialog).getByText('was 20/11/2026')).toBeInTheDocument();
    expect(dialog.textContent).toContain('20/11/2029');
  });

  it('shows no "was" when no row is marked changed', () => {
    const { dialog } = open(VIEW_480);
    expect(within(dialog).queryByText(/^was /)).not.toBeInTheDocument();
  });

  it('shows the line state and the PO when the page passes them', () => {
    const { dialog } = open(VIEW_480, { purchasingState: 'To Buy', po: '202609-S0086' });
    expect(dialog.textContent).toContain('To Buy');
    expect(dialog.textContent).toContain('202609-S0086');
  });

  it('Escape closes it and returns focus to the (i) button', () => {
    const { button, dialog } = open(VIEW_480);
    fireEvent.keyDown(dialog, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(document.activeElement).toBe(button);
  });

  it('Close returns focus to the (i) button too', () => {
    const { button, dialog } = open(VIEW_480);
    fireEvent.click(within(dialog).getAllByRole('button', { name: 'Close' })[0]);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(document.activeElement).toBe(button);
  });
});

describe('OrderSplitsDialog - the whole order', () => {
  const LINES = [
    { lineNo: 480, itemCode: 'CSK14B', view: VIEW_480 },
    { lineNo: 752, itemCode: 'CSK14B', view: VIEW_752 },
  ];

  it('is titled, counts the split lines and groups the rows by line in order', () => {
    render(
      <OrderSplitsDialog
        title="SO417636: splits"
        lines={LINES}
        open
        onOpenChange={() => {}}
      />,
    );
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('SO417636: splits')).toBeInTheDocument();
    expect(dialog.textContent).toContain('2 split lines');
    const text = dialog.textContent ?? '';
    const a = text.indexOf('Line 480 CSK14B');
    const b = text.indexOf('Line 752 CSK14B');
    expect(a).toBeGreaterThan(-1);
    expect(b).toBeGreaterThan(a);
    expect(text).toContain('Confirmed');
    expect(text).toContain('AutoCount changed');
    expect(text).toContain('AutoCount 417 @ 20/10/2026, now 14 @ 20/09/2026');
    expect(text).toContain('ORDER 145');
  });

  it('puts the subtitle (the SO number on the OI page) under the title', () => {
    render(
      <OrderSplitsDialog
        title="OI-2609-0578: splits"
        subtitle="SO417636"
        lines={LINES}
        open
        onOpenChange={() => {}}
      />,
    );
    expect(screen.getByRole('dialog').textContent).toContain('SO417636');
  });

  it('shows the empty state when no line is split', () => {
    render(<OrderSplitsDialog title="SO417636: splits" lines={[]} open onOpenChange={() => {}} />);
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('No split lines')).toBeInTheDocument();
    expect(within(dialog).getByText('Every line ships as AutoCount has it.')).toBeInTheDocument();
  });

  it('renders nothing while closed', () => {
    render(<OrderSplitsDialog title="SO417636: splits" lines={LINES} open={false} onOpenChange={() => {}} />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});

/**
 * Review round 1 (UAC B5a): the popups render their rows through the shared DataGrid, and the
 * total is a line of text ("Total 417 ..."), not a table row.
 */
describe('B5a: shared DataGrid, total as text', () => {
  const GRID = '[data-slot="data-grid-table"]';

  it('the line popup holds exactly one DataGrid and "Total 417" is text outside any table row', () => {
    info(VIEW_480);
    const button = screen.getByRole('button', { name: 'Show the splits of line 480' });
    button.focus();
    fireEvent.click(button);
    const dialog = screen.getByRole('dialog');
    expect(dialog.querySelectorAll(GRID)).toHaveLength(1);
    const total = within(dialog).getByText(/Total 417/);
    expect(total.closest('tr')).toBeNull();
    expect(total.textContent).toContain('AutoCount 417 @ 20/10/2026, now 14 @ 20/09/2026');
  });

  it('the whole-order popup holds one DataGrid per split line, each under its own heading', () => {
    render(
      <OrderSplitsDialog
        title="SO417636: splits"
        lines={[
          { lineNo: 480, itemCode: 'CSK14B', view: VIEW_480 },
          { lineNo: 752, itemCode: 'CSK14B', view: VIEW_752 },
        ]}
        open
        onOpenChange={() => {}}
      />,
    );
    const dialog = screen.getByRole('dialog');
    expect(dialog.querySelectorAll(GRID)).toHaveLength(2);
    expect(within(dialog).getByText(/Line 480 CSK14B/).closest('tr')).toBeNull();
    expect(within(dialog).getByText(/Line 752 CSK14B/).closest('tr')).toBeNull();
  });
});
