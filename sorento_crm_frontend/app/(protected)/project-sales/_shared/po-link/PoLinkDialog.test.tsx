/**
 * AC-LINK-CRM-UI: the Link to PO popup (mock v4, approved 4 Nov). The services are mocked at
 * their boundary; the real hooks, DataGrid and wording run.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  PoLinkCapabilities,
  PoLinkOption,
  PoLinkResult,
  SnapshotLine,
} from '../../stock-debt/types/stockDebtSnapshot.types';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    value?: string;
    onChange: (value: string) => void;
    options?: { value: string; label: string; disabled?: boolean; description?: string }[];
    placeholder?: string;
    truncateTriggerLabel?: boolean;
    clearable?: boolean;
  }) => (
    <select
      id={props.id}
      data-clearable={props.clearable ? 'true' : 'false'}
      data-truncate={props.truncateTriggerLabel ? 'true' : 'false'}
      value={props.value ?? ''}
      onChange={(event) => props.onChange(event.target.value)}
    >
      <option value="">{props.placeholder ?? ''}</option>
      {(props.options ?? []).map((option) => (
        <option key={option.value} value={option.value} disabled={option.disabled} title={option.description}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

const linkPoLines = vi.fn();
const changePoLines = vi.fn();
const relocatePoLine = vi.fn();
const unlinkPoLines = vi.fn();
const resumePoLink = vi.fn();
vi.mock('../../stock-debt/services/stockDebtSnapshotService', () => ({
  linkPoLines: (...args: unknown[]) => linkPoLines(...args),
  unlinkPoLines: (...args: unknown[]) => unlinkPoLines(...args),
  relinkPoLines: vi.fn(),
  changePoLines: (...args: unknown[]) => changePoLines(...args),
  relocatePoLine: (...args: unknown[]) => relocatePoLine(...args),
  resumePoLink: (...args: unknown[]) => resumePoLink(...args),
  getPoLinkOptions: vi.fn(),
  getSnapshot: vi.fn(),
  getSnapshotRowLines: vi.fn(),
  listSnapshotRows: vi.fn(),
  listSnapshots: vi.fn(),
  createSnapshot: vi.fn(),
  exportSnapshot: vi.fn(),
  setSnapshotDecision: vi.fn(),
}));

import { PoLinkDialog } from './PoLinkDialog';
import { snapshotPoLinkTarget } from '../../stock-debt/lib/poLinkTarget';

const CAPS: PoLinkCapabilities = {
  split_link: { enabled: true, reason: null },
  link_row: { enabled: false, reason: 'Waiting for AutoCount' },
  unlink_row: { enabled: false, reason: 'Waiting for AutoCount' },
  relink_row: { enabled: false, reason: 'Waiting for AutoCount' },
};

const PO_LINES: PoLinkOption[] = [
  {
    po_line_id: 'po-3', po_number: '202609-S0029', po_line_no: 3, location_code: 'HQ',
    delivery_date: '2026-11-12', po_qty: 500, free_qty: 380, supplier_name: 'Supplier A',
    book: 'DB3',
  },
  {
    po_line_id: 'po-7', po_number: '202610-S0007', po_line_no: 1, location_code: 'MWH-BB',
    delivery_date: '2026-11-20', po_qty: 120, free_qty: 120, supplier_name: 'Supplier A',
    book: 'DB3',
  },
  {
    po_line_id: 'po-live', po_number: '202609-S0064', po_line_no: 2, location_code: 'HQ',
    delivery_date: '2026-11-25', po_qty: 300, free_qty: 300, supplier_name: 'Supplier B',
    book: 'LIVE',
  },
];

function soLine(over: Partial<SnapshotLine>): SnapshotLine {
  return {
    so_number: 'SO425045', line_no: 140, agent_code: null, warehouse_code: 'MWH-BB',
    required_date: '2026-11-18', open_qty: 120, assigned_qty: 0, assigned_source: null,
    status: 'short', short_qty: 120, bucket: '2026-11', sales_order_line_id: 'sol-1',
    oi_rows: [], now: { so_status: 'open', open_qty: 120, po_links: [] },
    ...over,
  } as SnapshotLine;
}

function result(over: Partial<PoLinkResult>): PoLinkResult {
  return {
    sales_order_line_id: 'sol-1', so_number: 'SO425045', so_line_no: 140, po_number: '202609-S0029',
    qty: 120, outcome: 'done', error_code: null, warnings: [], message: '', operation_id: null,
    company_code: 'SRT', po_line_id: 'pol-new', ...over,
  };
}

function renderDialog(lines = [soLine({})], mode: 'link' | 'change' | 'unlink' = 'link') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onClose = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <PoLinkDialog
        mode={mode}
        target={snapshotPoLinkTarget('snap', 'row')}
        lines={lines}
        allLines={lines}
        capabilities={CAPS}
        poLines={PO_LINES}
        soBooks={{ 'sol-1': 'DB3', 'sol-2': 'DB3', 'sol-c': 'DB3', 'sol-p': 'DB3' }}
        onClose={onClose}
      />
    </QueryClientProvider>,
  );
  return { dialog: screen.getByTestId('po-link-dialog'), onClose };
}

beforeEach(() => {
  linkPoLines.mockReset();
  changePoLines.mockReset();
  unlinkPoLines.mockReset();
  relocatePoLine.mockReset();
  resumePoLink.mockReset();
});

describe('Link to PO popup', () => {
  it('one ticked row per line with Location, Delivery date, Outstanding, PO, PO qty, Free and Qty', () => {
    const { dialog } = renderDialog();
    const headers = within(dialog).getAllByRole('columnheader').map((cell) => cell.textContent);
    expect(headers.slice(1)).toEqual([
      'Sales order', 'Location', 'Delivery date', 'Outstanding', 'PO', 'PO qty', 'Free', 'Qty',
    ]);
    expect(dialog).toHaveTextContent('18/11/2026');
    expect(within(dialog).getByRole('checkbox', { name: /select so425045 line 140/i })).toBeChecked();
    expect(dialog).toHaveTextContent('1 of 1 lines');
  });

  it('the PO picker truncates its label so the clear button never overlaps it (375 px)', () => {
    const { dialog } = renderDialog();
    expect(dialog.querySelector('#po-link-po-sol-1')).toHaveAttribute('data-truncate', 'true');
  });

  it('the PO picker shows only the PO number (owner, 5 Nov: "just show me the PO number")', () => {
    const { dialog } = renderDialog();
    const options = [...(dialog.querySelector('#po-link-po-sol-1') as HTMLSelectElement).options];
    expect(options.slice(1).map((o) => o.textContent)).toEqual([
      '202609-S0029', '202610-S0007', '202609-S0064',
    ]);
    // No line, location, free qty, arrival or supplier text on an option.
    expect(options.slice(1).map((o) => o.title).filter(Boolean)).toEqual(['In another AutoCount book from this sales order']);
  });

  it('two lines of one PO tell themselves apart by the AutoCount line number in brackets', () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <PoLinkDialog
          mode="link" target={snapshotPoLinkTarget('snap', 'row')} lines={[soLine({})]} allLines={[soLine({})]}
          capabilities={CAPS}
          poLines={[PO_LINES[0], { ...PO_LINES[0], po_line_id: 'po-3b', po_line_no: 5, free_qty: 40 }]}
          soBooks={{ 'sol-1': 'DB3' }}
          onClose={vi.fn()}
        />
      </QueryClientProvider>,
    );
    const options = [...(document.querySelector('#po-link-po-sol-1') as HTMLSelectElement).options];
    expect(options.slice(1).map((o) => o.textContent)).toEqual(['202609-S0029 (3)', '202609-S0029 (5)']);
  });

  it('a line already covered by a PO is greyed "Already covered by PO …" and cannot be ticked', () => {
    const covered = soLine({
      sales_order_line_id: 'sol-c', open_qty: 10,
      now: {
        so_status: 'open', open_qty: 10,
        po_links: [{ po_line_id: 'x', po_number: 'FXT-1104d-1', po_line_no: 3, qty: 10, location_code: 'BRW-AM' }],
      },
    });
    const { dialog } = renderDialog([covered]);
    expect(dialog).toHaveTextContent('Already covered by PO FXT-1104d-1 (10)');
    const box = within(dialog).getByRole('checkbox', { name: /select so425045 line 140/i });
    expect(box).not.toBeChecked();
    expect(box).toBeDisabled();
    expect(within(dialog).getByRole('button', { name: 'Link 0 lines' })).toBeDisabled();
  });

  it('a partly covered line defaults Qty to what is left (outstanding minus linked)', () => {
    const partly = soLine({
      sales_order_line_id: 'sol-p', open_qty: 120,
      now: {
        so_status: 'open', open_qty: 120,
        po_links: [{ po_line_id: 'x', po_number: 'FXT-1104d-1', po_line_no: 3, qty: 100, location_code: 'HQ' }],
      },
    });
    const { dialog } = renderDialog([partly]);
    fireEvent.change(dialog.querySelector('#po-link-po-sol-p') as HTMLSelectElement, {
      target: { value: 'po-3' },
    });
    expect((dialog.querySelector('#po-link-qty-sol-p') as HTMLInputElement).value).toBe('20');
  });

  it('a PO in another AutoCount book is greyed with the reason', () => {
    const { dialog } = renderDialog();
    const live = [...(dialog.querySelector('#po-link-po-sol-1') as HTMLSelectElement).options].find(
      (o) => o.value === 'po-live',
    ) as HTMLOptionElement;
    expect(live.disabled).toBe(true);
    expect(live.title).toContain('In another AutoCount book');
  });

  it('picking a PO shows its PO qty and Free, and Qty defaults to the outstanding', () => {
    const { dialog } = renderDialog();
    fireEvent.change(dialog.querySelector('#po-link-po-sol-1') as HTMLSelectElement, {
      target: { value: 'po-3' },
    });
    const row = within(dialog).getAllByRole('row')[1];
    expect(row).toHaveTextContent('500');
    expect(row).toHaveTextContent('380');
    expect((dialog.querySelector('#po-link-qty-sol-1') as HTMLInputElement).value).toBe('120');
  });

  it('sends the picked PO line and qty, then shows the result in plain words', async () => {
    linkPoLines.mockResolvedValue({ results: [result({})] });
    const { dialog } = renderDialog();
    fireEvent.change(dialog.querySelector('#po-link-po-sol-1') as HTMLSelectElement, {
      target: { value: 'po-3' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Link 1 line' }));
    await waitFor(() =>
      expect(linkPoLines).toHaveBeenCalledWith('snap', 'row', [
        { sales_order_line_id: 'sol-1', po_line_id: 'po-3', qty: 120 },
      ]),
    );
    const card = await screen.findByTestId('po-link-result');
    expect(card).toHaveTextContent('Linked');
    expect(card).toHaveTextContent('SO425045 line 140 now covered by PO 202609-S0029 (120).');
    expect(card).not.toHaveTextContent(/[A-Z]{3,}_[A-Z]/);
  });

  it('a row with no PO picked blocks the send', async () => {
    const { dialog } = renderDialog();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Link 1 line' }));
    expect(await within(dialog).findByText('No PO line picked')).toBeInTheDocument();
    expect(linkPoLines).not.toHaveBeenCalled();
  });

  it('linking a whole PO line waits for AutoCount while that is off', async () => {
    const { dialog } = renderDialog();
    fireEvent.change(dialog.querySelector('#po-link-po-sol-1') as HTMLSelectElement, {
      target: { value: 'po-7' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Link 1 line' }));
    expect(
      await within(dialog).findByText('Linking the whole PO line: Waiting for AutoCount'),
    ).toBeInTheDocument();
    expect(linkPoLines).not.toHaveBeenCalled();
  });

  it('a location not moved offers the move, which calls relocate with the new line', async () => {
    linkPoLines.mockResolvedValue({ results: [result({ warnings: ['LOCATION_NOT_MOVED'] })] });
    relocatePoLine.mockResolvedValue(result({ outcome: 'done' }));
    const { dialog } = renderDialog();
    fireEvent.change(dialog.querySelector('#po-link-po-sol-1') as HTMLSelectElement, {
      target: { value: 'po-3' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Link 1 line' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Move to the sales order location' }));
    await waitFor(() =>
      expect(relocatePoLine).toHaveBeenCalledWith('pol-new'),
    );
    await waitFor(() => expect(screen.getByTestId('po-link-result')).toHaveTextContent(/^Linked/));
  });

  it('two lines on one PO line cannot take more than it has free', async () => {
    const lines = [soLine({}), soLine({ sales_order_line_id: 'sol-2', so_number: 'SO425046', line_no: 3, open_qty: 300, now: { so_status: 'open', open_qty: 300, po_links: [] } })];
    const { dialog } = renderDialog(lines);
    for (const id of ['sol-1', 'sol-2']) {
      fireEvent.change(dialog.querySelector(`#po-link-po-${id}`) as HTMLSelectElement, {
        target: { value: 'po-3' },
      });
    }
    fireEvent.click(within(dialog).getByRole('button', { name: 'Link 2 lines' }));
    expect(await within(dialog).findAllByText('PO 202609-S0029 has 380 free in total')).not.toHaveLength(0);
    expect(linkPoLines).not.toHaveBeenCalled();
  });

  it('needs attention offers Resume, which asks the Shared Service and never re-sends the link', async () => {
    linkPoLines.mockResolvedValue({
      results: [result({ outcome: 'needs_attention', operation_id: 'op-9', error_code: 'VENDOR_ERROR' })],
    });
    resumePoLink.mockResolvedValue(result({ outcome: 'done' }));
    const { dialog } = renderDialog();
    fireEvent.change(dialog.querySelector('#po-link-po-sol-1') as HTMLSelectElement, {
      target: { value: 'po-3' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Link 1 line' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Resume' }));
    await waitFor(() =>
      expect(resumePoLink).toHaveBeenCalledWith({
        operationId: 'op-9', poLineId: 'pol-new', salesOrderLineId: 'sol-1',
      }),
    );
    expect(linkPoLines).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.getByTestId('po-link-result')).toHaveTextContent('Linked'));
  });
});

describe('Change PO popup (STOCKDEBT-LIVE-ACTIONS, owner card 11 Nov)', () => {
  const covered = soLine({
    status: 'pinned', short_qty: 0, assigned_qty: 120,
    now: {
      so_status: 'open', open_qty: 120,
      po_links: [{ po_line_id: 'po-7', po_number: '202610-S0007', po_line_no: 1, qty: 120, open_qty: 120, location_code: 'MWH-BB' }],
    },
  });

  it('shows the PO now covering the line and a picker without it', () => {
    const { dialog } = renderDialog([covered], 'change');
    const headers = within(dialog).getAllByRole('columnheader').map((cell) => cell.textContent);
    expect(headers.slice(1)).toEqual([
      'Sales order', 'Location', 'Delivery date', 'Outstanding', 'PO', 'Open', 'Change to', 'Free',
    ]);
    expect(dialog).toHaveTextContent('202610-S0007 · line 1');
    const options = [...(dialog.querySelector('[id="po-link-change-sol-1:po-7"]') as HTMLSelectElement).options];
    expect(options.slice(1).map((o) => o.value)).toEqual(['po-3', 'po-live']);
  });

  it('refuses a PO line with less free than the linked qty, and sends nothing', async () => {
    const { dialog } = renderDialog([{ ...covered, now: { ...covered.now, po_links: [{ ...covered.now.po_links![0], qty: 400, open_qty: 400 }] } }], 'change');
    fireEvent.change(dialog.querySelector('[id="po-link-change-sol-1:po-7"]') as HTMLSelectElement, { target: { value: 'po-3' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Change 1 line' }));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('PO 202609-S0029 has only 380 free');
    expect(changePoLines).not.toHaveBeenCalled();
  });

  it('sends the SO line and the new PO line, then shows both halves in plain words, unlink first', async () => {
    changePoLines.mockResolvedValue({
      results: [
        result({ action: 'unlink', po_number: '202610-S0007' }),
        result({ action: 'link', po_number: '202609-S0029' }),
      ],
    });
    const { dialog } = renderDialog([covered], 'change');
    fireEvent.change(dialog.querySelector('[id="po-link-change-sol-1:po-7"]') as HTMLSelectElement, { target: { value: 'po-3' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Change 1 line' }));
    await waitFor(() => expect(changePoLines).toHaveBeenCalledWith('snap', 'row', [
      { sales_order_line_id: 'sol-1', po_line_id: 'po-3', from_po_line_id: 'po-7' },
    ]));
    const cards = await within(dialog).findAllByTestId('po-link-result');
    expect(cards.map((card) => card.textContent)).toEqual([
      'UnlinkedSO425045 line 140 is no longer covered by PO 202610-S0007 (120).',
      'LinkedSO425045 line 140 now covered by PO 202609-S0029 (120).',
    ]);
  });

  it('moves only the open balance: a line with 50 of 120 received shows Open 70', () => {
    const { dialog } = renderDialog(
      [{ ...covered, now: { ...covered.now, po_links: [{ ...covered.now.po_links![0], open_qty: 70 }] } }],
      'change',
    );
    const headers = within(dialog).getAllByRole('columnheader').map((cell) => cell.textContent);
    const cells = within(within(dialog).getAllByRole('row')[1]).getAllByRole('cell');
    expect(cells[headers.indexOf('Open')]).toHaveTextContent(/^70$/);
  });
});

describe('Change PO: a line covered by two PO lines is one row per PO line (owner, 13 Nov)', () => {
  const twoPos = soLine({
    status: 'pinned', short_qty: 0, assigned_qty: 120,
    now: {
      so_status: 'open', open_qty: 120,
      po_links: [
        { po_line_id: 'po-7', po_number: '202610-S0007', po_line_no: 1, qty: 60, open_qty: 60, location_code: 'MWH-BB' },
        { po_line_id: 'po-live', po_number: '202609-S0064', po_line_no: 2, qty: 40, open_qty: 35, location_code: 'HQ' },
      ],
    },
  });

  it('shows each PO with its Open qty and its own Change to picker, and never "Covered by more than one PO line"', () => {
    const { dialog } = renderDialog([twoPos], 'change');
    expect(dialog).not.toHaveTextContent('Covered by more than one PO line');
    expect(dialog).not.toHaveTextContent('No PO linked');
    expect(dialog).toHaveTextContent('202610-S0007 · line 1');
    expect(dialog).toHaveTextContent('202609-S0064 · line 2');
    expect(dialog.querySelector('[id="po-link-change-sol-1:po-7"]')).not.toBeNull();
    expect(dialog.querySelector('[id="po-link-change-sol-1:po-live"]')).not.toBeNull();
    expect(dialog).toHaveTextContent('35');
  });

  it('sends only the ticked row, carrying its from_po_line_id', async () => {
    changePoLines.mockResolvedValue({ results: [result({ action: 'unlink' }), result({ action: 'link' })] });
    const { dialog } = renderDialog([twoPos], 'change');
    fireEvent.change(dialog.querySelector('[id="po-link-change-sol-1:po-live"]') as HTMLSelectElement, {
      target: { value: 'po-3' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Change 1 line' }));
    await waitFor(() =>
      expect(changePoLines).toHaveBeenCalledWith('snap', 'row', [
        { sales_order_line_id: 'sol-1', po_line_id: 'po-3', from_po_line_id: 'po-live' },
      ]),
    );
  });
});

describe('A refused or failed result offers Try again (D3)', () => {
  it.each(['refused', 'vendor_error'] as const)('a %s card re-sends exactly that line and shows the new result', async (outcome) => {
    linkPoLines
      .mockResolvedValueOnce({
        results: [result({ outcome, error_code: outcome === 'refused' ? 'FIELD_REQUIRED' : 'VENDOR_ERROR', message: 'PurchaseAgent is required.' })],
      })
      .mockResolvedValueOnce({ results: [result({ outcome: 'done' })] });
    const { dialog } = renderDialog();
    fireEvent.change(dialog.querySelector('#po-link-po-sol-1') as HTMLSelectElement, { target: { value: 'po-3' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Link 1 line' }));
    const card = await screen.findByTestId('po-link-result');
    const retry = await within(card).findByRole('button', { name: /try again/i });
    fireEvent.click(retry);
    await waitFor(() => expect(linkPoLines).toHaveBeenCalledTimes(2));
    expect(linkPoLines.mock.calls[1]).toEqual([
      'snap', 'row', [{ sales_order_line_id: 'sol-1', po_line_id: 'po-3', qty: 120 }],
    ]);
    await waitFor(() => expect(screen.getByTestId('po-link-result')).toHaveTextContent('Linked'));
    expect(within(screen.getByTestId('po-link-result')).queryByRole('button', { name: /try again/i })).toBeNull();
  });
});

describe('A skipped line in a batch (plain reason, Try again)', () => {
  it('shows the SO number and line with the message, never the code, and offers Try again', async () => {
    linkPoLines.mockResolvedValue({
      results: [
        result({
          outcome: 'skipped', error_code: 'QTY_ABOVE_OUTSTANDING',
          message: 'SO425045 line 140 was not linked: it needs less than that now.',
        }),
      ],
    });
    const { dialog } = renderDialog();
    fireEvent.change(dialog.querySelector('#po-link-po-sol-1') as HTMLSelectElement, { target: { value: 'po-3' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Link 1 line' }));
    const card = await screen.findByTestId('po-link-result');
    expect(card).toHaveTextContent('SO425045 line 140');
    expect(card).toHaveTextContent('it needs less than that now');
    expect(document.body).not.toHaveTextContent('QTY_ABOVE_OUTSTANDING');
    expect(within(card).getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });
});

describe('No "Line" column in the popup (owner round, 13 Nov)', () => {
  const covered = soLine({
    status: 'pinned', short_qty: 0, assigned_qty: 120,
    now: {
      so_status: 'open', open_qty: 120,
      po_links: [{ po_line_id: 'po-7', po_number: '202610-S0007', po_line_no: 1, qty: 120, open_qty: 120, location_code: 'MWH-BB' }],
    },
  });

  it.each(['link', 'change', 'unlink'] as const)('%s mode has no Line column header and still shows the SO number', (mode) => {
    const { dialog } = renderDialog([mode === 'link' ? soLine({}) : covered], mode);
    const headers = within(dialog).getAllByRole('columnheader').map((cell) => (cell.textContent ?? '').trim());
    expect(headers).not.toContain('Line');
    expect(headers).toContain('Sales order');
    expect(dialog).toHaveTextContent('SO425045');
  });

  it('the result card still says "line N"', async () => {
    linkPoLines.mockResolvedValue({ results: [result({ so_line_no: 16 })] });
    const { dialog } = renderDialog();
    fireEvent.change(dialog.querySelector('#po-link-po-sol-1') as HTMLSelectElement, { target: { value: 'po-3' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Link 1 line' }));
    expect(await screen.findByTestId('po-link-result')).toHaveTextContent('SO425045 line 16');
  });
});

describe('Change PO results offer Try again (db3 step 10)', () => {
  const covered = soLine({
    status: 'pinned', short_qty: 0, assigned_qty: 120,
    now: {
      so_status: 'open', open_qty: 120,
      po_links: [{ po_line_id: 'po-7', po_number: '202610-S0007', po_line_no: 1, qty: 60, open_qty: 60, location_code: 'MWH-BB' }],
    },
  });
  async function change() {
    const { dialog } = renderDialog([covered], 'change');
    fireEvent.change(dialog.querySelector('[id="po-link-change-sol-1:po-7"]') as HTMLSelectElement, { target: { value: 'po-3' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Change 1 line' }));
    return dialog;
  }

  it.each(['refused', 'vendor_error'] as const)('(a) an unlink that is %s shows Try again, which re-sends the change for that SO line', async (outcome) => {
    changePoLines
      .mockResolvedValueOnce({ results: [result({ action: 'unlink', outcome, po_number: '202610-S0007', po_line_id: 'po-7', message: 'AutoCount said no.' })] })
      .mockResolvedValueOnce({ results: [result({ action: 'unlink', po_number: '202610-S0007' }), result({ action: 'link', po_number: '202609-S0029' })] });
    const dialog = await change();
    const card = await within(dialog).findByTestId('po-link-result');
    fireEvent.click(await within(card).findByRole('button', { name: /try again/i }));
    await waitFor(() => expect(changePoLines).toHaveBeenCalledTimes(2));
    expect(changePoLines.mock.calls[1]).toEqual([
      'snap', 'row', [{ sales_order_line_id: 'sol-1', po_line_id: 'po-3', from_po_line_id: 'po-7' }],
    ]);
    await waitFor(() => expect(within(dialog).queryByRole('button', { name: /try again/i })).toBeNull());
    expect(dialog).toHaveTextContent('Unlinked');
  });

  it('(b) an unlink done but a link not done shows Try again on the link card, which sends a plain link', async () => {
    changePoLines.mockResolvedValueOnce({
      results: [
        result({ action: 'unlink', po_number: '202610-S0007', po_line_id: 'po-7' }),
        result({
          action: 'link', outcome: 'refused', po_number: '202609-S0029', po_line_id: 'po-3', qty: 60,
          unlinked_po: '202610-S0007', message: 'AutoCount said no.',
        }),
      ],
    });
    linkPoLines.mockResolvedValue({ results: [result({ action: 'link', po_number: '202609-S0029', qty: 60 })] });
    const dialog = await change();
    const cards = await within(dialog).findAllByTestId('po-link-result');
    expect(cards).toHaveLength(2);
    expect(within(cards[0]).queryByRole('button', { name: /try again/i })).toBeNull();
    fireEvent.click(await within(cards[1]).findByRole('button', { name: /try again/i }));
    await waitFor(() =>
      expect(linkPoLines).toHaveBeenCalledWith('snap', 'row', [
        { sales_order_line_id: 'sol-1', po_line_id: 'po-3', qty: 60 },
      ]),
    );
    await waitFor(() => expect(within(dialog).queryByRole('button', { name: /try again/i })).toBeNull());
    expect(changePoLines).toHaveBeenCalledTimes(1);
  });
});

// Owner, 13 Nov 18:55: "1 button is like link po then they can link or change link or unlink in the
// popup". One grid, mode `manage`, titled "Link PO".
describe('Link PO popup (mode manage)', () => {
  const MANAGE_CAPS: PoLinkCapabilities = {
    split_link: { enabled: true, reason: null },
    link_row: { enabled: false, reason: null },
    unlink_row: { enabled: true, reason: null },
    relink_row: { enabled: false, reason: null },
  };
  const linked = (id: string, so: string, poId: string, poNo: string, qty: number, over: Partial<SnapshotLine> = {}) =>
    soLine({
      sales_order_line_id: id, so_number: so, open_qty: qty,
      now: {
        so_status: 'open', open_qty: qty,
        po_links: [{ po_line_id: poId, po_number: poNo, po_line_no: 1, qty, open_qty: qty, location_code: 'MWH-BB' }],
      },
      ...over,
    });

  function renderManage(lines: SnapshotLine[], caps: PoLinkCapabilities = MANAGE_CAPS) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <PoLinkDialog
          mode={'manage' as never}
          target={snapshotPoLinkTarget('snap', 'row')}
          lines={lines}
          allLines={lines}
          capabilities={caps}
          poLines={PO_LINES}
          soBooks={{ 'sol-1': 'DB3', 'sol-2': 'DB3', 'sol-c': 'DB3', 'sol-p': 'DB3' }}
          onClose={vi.fn()}
        />
      </QueryClientProvider>,
    );
    return screen.getByTestId('po-link-dialog');
  }
  const rowOf = (dialog: HTMLElement, text: string) =>
    within(dialog).getAllByRole('row').find((row) => (row.textContent ?? '').includes(text)) as HTMLElement;
  const picker = (row: HTMLElement) => within(row).getAllByRole('combobox').slice(-2)[0] as HTMLSelectElement;
  const optionNamed = (select: HTMLSelectElement, pattern: RegExp) =>
    [...select.options].find((o) => pattern.test(o.textContent ?? '')) as HTMLOptionElement;
  function choose(select: HTMLSelectElement, pattern: RegExp) {
    fireEvent.change(select, { target: { value: optionNamed(select, pattern).value } });
  }

  it('is titled Link PO and has the columns tick, Sales order, Location, Delivery date, Outstanding, PO, Action', () => {
    const dialog = renderManage([linked('sol-1', 'SO425045', 'po-7', '202610-S0007', 120)]);
    expect(within(dialog).getByText('Link PO')).toBeInTheDocument();
    const headers = within(dialog).getAllByRole('columnheader').map((cell) => (cell.textContent ?? '').trim());
    expect(headers.slice(1)).toEqual(['Sales order', 'Location', 'Delivery date', 'Outstanding', 'PO', 'Action']);
  });

  it('one row per (SO line, linked PO line) plus a new row for a line that still needs qty or has no PO', () => {
    const partly = linked('sol-1', 'SO425045', 'po-7', '202610-S0007', 60, {
      now: { so_status: 'open', open_qty: 120, po_links: [{ po_line_id: 'po-7', po_number: '202610-S0007', po_line_no: 1, qty: 60, open_qty: 60, location_code: 'MWH-BB' }] },
    });
    const full = linked('sol-2', 'SO425046', 'po-live', '202609-S0064', 120);
    const bare = soLine({ sales_order_line_id: 'sol-c', so_number: 'SO425047' });
    const dialog = renderManage([partly, full, bare]);
    const bodyRows = within(dialog).getAllByRole('row').slice(1);
    // partly covered: linked row + new row; fully covered: one row; no PO: one new row.
    expect(bodyRows).toHaveLength(4);
    expect(bodyRows.filter((r) => (r.textContent ?? '').includes('SO425045'))).toHaveLength(2);
    expect(bodyRows.filter((r) => (r.textContent ?? '').includes('SO425046'))).toHaveLength(1);
    expect(bodyRows.filter((r) => (r.textContent ?? '').includes('SO425047'))).toHaveLength(1);
  });

  it('a linked row offers Keep (default), Unlink and Change to each open PO line except the current one', () => {
    const dialog = renderManage([linked('sol-1', 'SO425045', 'po-7', '202610-S0007', 120)]);
    const select = picker(rowOf(dialog, '202610-S0007'));
    const labels = [...select.options].map((o) => (o.textContent ?? '').trim());
    expect(labels[0]).toBe('Keep');
    expect(select.value).toBe(select.options[0].value);
    expect(labels).toContain('Unlink');
    expect(labels.some((l) => /^Change to 202609-S0029/.test(l))).toBe(true);
    expect(labels.some((l) => /^Change to 202609-S0064/.test(l))).toBe(true);
    expect(labels.some((l) => /202610-S0007/.test(l))).toBe(false);
  });

  it('Save (n) sends unlink, then change (with from_po_line_id), then link; Keep rows are not sent', async () => {
    unlinkPoLines.mockResolvedValue({ results: [result({ action: 'unlink', po_number: '202610-S0007', po_line_id: 'po-7' })] });
    changePoLines.mockResolvedValue({ results: [result({ sales_order_line_id: 'sol-2', action: 'unlink' }), result({ sales_order_line_id: 'sol-2', action: 'link' })] });
    linkPoLines.mockResolvedValue({ results: [result({ sales_order_line_id: 'sol-c', qty: 40 })] });
    const keep = linked('sol-p', 'SO425044', 'po-live', '202609-S0064', 120);
    const dialog = renderManage([
      linked('sol-1', 'SO425045', 'po-7', '202610-S0007', 120),
      linked('sol-2', 'SO425046', 'po-live', '202609-S0064', 120),
      soLine({ sales_order_line_id: 'sol-c', so_number: 'SO425047', open_qty: 40, short_qty: 40 }),
      keep,
    ]);
    choose(picker(rowOf(dialog, 'SO425045')), /^Unlink$/);
    choose(picker(rowOf(dialog, 'SO425046')), /^Change to 202609-S0029/);
    const newRow = rowOf(dialog, 'SO425047');
    fireEvent.change(newRow.querySelector('select') as HTMLSelectElement, { target: { value: 'po-3' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save (3)' }));
    await waitFor(() => expect(linkPoLines).toHaveBeenCalled());
    expect(unlinkPoLines).toHaveBeenCalledWith('snap', 'row', ['po-7']);
    expect(changePoLines).toHaveBeenCalledWith('snap', 'row', [
      { sales_order_line_id: 'sol-2', po_line_id: 'po-3', from_po_line_id: 'po-live' },
    ]);
    expect(linkPoLines).toHaveBeenCalledWith('snap', 'row', [
      { sales_order_line_id: 'sol-c', po_line_id: 'po-3', qty: 40 },
    ]);
    const order = [unlinkPoLines, changePoLines, linkPoLines].map((fn) => fn.mock.invocationCallOrder[0]);
    expect([...order].sort((a, b) => a - b)).toEqual(order);
  });

  it('with nothing changed the main button has nothing to save', () => {
    const dialog = renderManage([linked('sol-1', 'SO425045', 'po-7', '202610-S0007', 120)]);
    const save = within(dialog).getByRole('button', { name: /^Save/ });
    expect(save).toBeDisabled();
  });

  it('shows every answer in one list in plain words, with Try again on a refusal', async () => {
    unlinkPoLines.mockResolvedValue({ results: [result({ action: 'unlink', po_number: '202610-S0007', po_line_id: 'po-7' })] });
    linkPoLines.mockResolvedValue({ results: [result({ sales_order_line_id: 'sol-c', outcome: 'refused', message: 'AutoCount said no.' })] });
    const dialog = renderManage([
      linked('sol-1', 'SO425045', 'po-7', '202610-S0007', 120),
      soLine({ sales_order_line_id: 'sol-c', so_number: 'SO425047', open_qty: 40, short_qty: 40 }),
    ]);
    choose(picker(rowOf(dialog, 'SO425045')), /^Unlink$/);
    fireEvent.change(rowOf(dialog, 'SO425047').querySelector('select') as HTMLSelectElement, { target: { value: 'po-3' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save (2)' }));
    const cards = await within(dialog).findAllByTestId('po-link-result');
    expect(cards.map((c) => c.textContent)).toEqual([
      expect.stringContaining('Unlinked'),
      expect.stringContaining('Not linked'),
    ]);
    expect(within(cards[1]).getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });

  it('an Action option AutoCount cannot do is disabled with its reason', () => {
    const caps = {
      ...MANAGE_CAPS,
      unlink_row: { enabled: false, reason: 'Waiting for AutoCount' },
      split_link: { enabled: false, reason: 'Switched off here' },
    };
    const dialog = renderManage([linked('sol-1', 'SO425045', 'po-7', '202610-S0007', 120)], caps);
    const select = picker(rowOf(dialog, '202610-S0007'));
    const unlink = optionNamed(select, /^Unlink/);
    expect(unlink.disabled).toBe(true);
    expect(`${unlink.title} ${unlink.textContent}`).toContain('Waiting for AutoCount');
    const change = optionNamed(select, /^Change to/);
    expect(change.disabled).toBe(true);
    expect(`${change.title} ${change.textContent}`).toContain('Switched off here');
  });

  // ---- review round (13 Nov)
  const bare = () => soLine({ sales_order_line_id: 'sol-c', so_number: 'SO425047', open_qty: 40, short_qty: 40 });

  it.each([
    ['above what the line still needs', 'po-3', '200'],
    ['above what the PO line has free', 'po-7', '130'],
  ])('a new row with a qty %s shows its error next to the field and Save sends nothing', async (_n, poId, typed) => {
    const dialog = renderManage([soLine({ sales_order_line_id: 'sol-c', so_number: 'SO425047', open_qty: 300, short_qty: 300 })]);
    const select = dialog.querySelector('[id="po-manage-po-sol-c:new"]') as HTMLSelectElement;
    fireEvent.change(select, { target: { value: poId } });
    fireEvent.change(dialog.querySelector('[id="po-manage-qty-sol-c:new"]') as HTMLInputElement, { target: { value: typed } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save (1)' }));
    const row = rowOf(dialog, 'SO425047');
    expect(await within(row).findByRole('alert')).toHaveTextContent(/\S/);
    expect(linkPoLines).not.toHaveBeenCalled();
    expect(changePoLines).not.toHaveBeenCalled();
    expect(unlinkPoLines).not.toHaveBeenCalled();
  });

  it('with split_link off a new row\'s PO line options are disabled with AutoCount\'s reason', () => {
    const dialog = renderManage([bare()], { ...MANAGE_CAPS, split_link: { enabled: false, reason: 'Switched off here' } });
    const options = [...(dialog.querySelector('[id="po-manage-po-sol-c:new"]') as HTMLSelectElement).options].filter((o) => o.value);
    expect(options.length).toBeGreaterThan(0);
    for (const option of options) {
      expect(option.disabled).toBe(true);
      expect(`${option.title} ${option.textContent}`).toContain('Switched off here');
    }
  });

  it('Try again on a failed change-link re-sends THAT change\'s PO line and qty, not the new row\'s', async () => {
    const partly = linked('sol-1', 'SO425045', 'po-7', '202610-S0007', 60, {
      now: { so_status: 'open', open_qty: 120, po_links: [{ po_line_id: 'po-7', po_number: '202610-S0007', po_line_no: 1, qty: 60, open_qty: 60, location_code: 'MWH-BB' }] },
    });
    changePoLines.mockResolvedValue({
      results: [
        result({ action: 'unlink', po_number: '202610-S0007', po_line_id: 'po-7', qty: 60 }),
        result({ action: 'link', outcome: 'refused', po_number: '202609-S0029', po_line_id: 'po-3', qty: 60, unlinked_po: '202610-S0007', message: 'AutoCount said no.' }),
      ],
    });
    linkPoLines
      .mockResolvedValueOnce({ results: [result({ action: 'link', po_number: '202609-S0064', po_line_id: 'po-live', qty: 50 })] })
      .mockResolvedValueOnce({ results: [result({ action: 'link', po_number: '202609-S0029', po_line_id: 'po-3', qty: 60 })] });
    const dialog = renderManage([partly]);
    choose(picker(rowOf(dialog, '202610-S0007')), /^Change to 202609-S0029/);
    fireEvent.change(dialog.querySelector('[id="po-manage-po-sol-1:new"]') as HTMLSelectElement, { target: { value: 'po-live' } });
    fireEvent.change(dialog.querySelector('[id="po-manage-qty-sol-1:new"]') as HTMLInputElement, { target: { value: '50' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save (2)' }));
    await waitFor(() => expect(linkPoLines).toHaveBeenCalledTimes(1));
    fireEvent.click(await within(dialog).findByRole('button', { name: /try again/i }));
    await waitFor(() => expect(linkPoLines).toHaveBeenCalledTimes(2));
    expect(linkPoLines.mock.calls[1]).toEqual([
      'snap', 'row', [{ sales_order_line_id: 'sol-1', po_line_id: 'po-3', qty: 60 }],
    ]);
  });

  it('a linked row\'s Action picker is clearable, and clearing it back to Keep leaves the row ticked', () => {
    const dialog = renderManage([linked('sol-1', 'SO425045', 'po-7', '202610-S0007', 120)]);
    const row = rowOf(dialog, '202610-S0007');
    const select = picker(row);
    expect(select.dataset.clearable).toBe('true');
    choose(select, /^Unlink$/);
    const box = within(row).getAllByRole('checkbox')[0];
    expect(box).toHaveAttribute('aria-checked', 'true');
    fireEvent.change(select, { target: { value: '' } });
    expect(box).toHaveAttribute('aria-checked', 'true');
    expect(within(dialog).getByRole('button', { name: /^Save/ })).toBeDisabled();
  });
});


// OI-PO-LINK owner hand test round (14 Nov): AC-HT1-e and AC-HT2a.
// ASSUMPTION: the dialog takes the options response's `so_products` as a prop `soProducts`
// (sales_order_line_id -> product id) and each PO option carries `product_id`.
describe('Link PO popup: rows of several products and the Qty / Action columns', () => {
  const MANAGE_CAPS: PoLinkCapabilities = {
    split_link: { enabled: true, reason: null },
    link_row: { enabled: false, reason: null },
    unlink_row: { enabled: true, reason: null },
    relink_row: { enabled: false, reason: null },
  };
  const PRODUCT_PO_LINES = [
    { ...PO_LINES[0], product_id: 'prod-A' },
    { ...PO_LINES[1], product_id: 'prod-B' },
    { ...PO_LINES[2], product_id: 'prod-A', book: 'DB3' },
  ] as PoLinkOption[];

  function renderMulti(lines: SnapshotLine[], soProducts: Record<string, string>) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <PoLinkDialog
          mode={'manage' as never}
          target={snapshotPoLinkTarget('snap', 'row')}
          lines={lines}
          allLines={lines}
          capabilities={MANAGE_CAPS}
          poLines={PRODUCT_PO_LINES}
          soBooks={{ 'sol-1': 'DB3', 'sol-2': 'DB3', 'sol-3': 'DB3' }}
          {...({ soProducts } as object)}
          onClose={vi.fn()}
        />
      </QueryClientProvider>,
    );
    return screen.getByTestId('po-link-dialog');
  }
  const newLine = (id: string, so: string) =>
    soLine({ sales_order_line_id: id, so_number: so, open_qty: 40, short_qty: 40 });
  const labelsOf = (dialog: HTMLElement, id: string) =>
    [...(dialog.querySelector(`[id="po-manage-po-${id}:new"]`) as HTMLSelectElement).options]
      .filter((o) => o.value)
      .map((o) => o.textContent);
  const rowOf = (dialog: HTMLElement, text: string) =>
    within(dialog).getAllByRole('row').find((row) => (row.textContent ?? '').includes(text)) as HTMLElement;

  it('AC-HT1-e: each new row offers only the PO lines of its own product', () => {
    const dialog = renderMulti(
      [newLine('sol-1', 'SO425045'), newLine('sol-2', 'SO425046')],
      { 'sol-1': 'prod-A', 'sol-2': 'prod-B' },
    );
    expect(labelsOf(dialog, 'sol-1')).toEqual(['202609-S0029', '202609-S0064']);
    expect(labelsOf(dialog, 'sol-2')).toEqual(['202610-S0007']);
  });

  it('AC-HT1-e: a row whose product has no PO line with free qty says so in that row and the others still Save', async () => {
    linkPoLines.mockResolvedValue({ results: [result({ sales_order_line_id: 'sol-1', qty: 40 })] });
    const dialog = renderMulti(
      [newLine('sol-1', 'SO425045'), newLine('sol-3', 'SO425047')],
      { 'sol-1': 'prod-A', 'sol-3': 'prod-C' },
    );
    expect(rowOf(dialog, 'SO425047')).toHaveTextContent('No PO line has stock free for this product.');
    expect(rowOf(dialog, 'SO425045')).not.toHaveTextContent('No PO line has stock free for this product.');
    expect(labelsOf(dialog, 'sol-3')).toEqual([]);
    fireEvent.change(dialog.querySelector('[id="po-manage-po-sol-1:new"]') as HTMLSelectElement, {
      target: { value: 'po-3' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save (1)' }));
    await waitFor(() =>
      expect(linkPoLines).toHaveBeenCalledWith('snap', 'row', [
        { sales_order_line_id: 'sol-1', po_line_id: 'po-3', qty: 40 },
      ]),
    );
  });

  const headerTexts = (dialog: HTMLElement) =>
    within(within(dialog).getAllByRole('row')[0]).getAllByRole('columnheader').map((c) => (c.textContent ?? '').trim());
  const columnOf = (cell: Element | null) => {
    const td = (cell as HTMLElement).closest('td,[role="cell"]') as HTMLElement;
    return [...(td.parentElement as HTMLElement).children].indexOf(td);
  };
  const linkedLine = soLine({
    sales_order_line_id: 'sol-2', so_number: 'SO425046', open_qty: 120,
    now: {
      so_status: 'open', open_qty: 120,
      po_links: [{ po_line_id: 'po-7', po_number: '202610-S0007', po_line_no: 1, qty: 120, open_qty: 120, location_code: 'MWH-BB' }],
    },
  });

  it('AC-HT2a: with only a new row there is a Qty column holding the qty box and no Action column', () => {
    const dialog = renderMulti([newLine('sol-1', 'SO425045')], { 'sol-1': 'prod-A' });
    const headers = headerTexts(dialog);
    expect(headers).toContain('Qty');
    expect(headers).not.toContain('Action');
    const qty = dialog.querySelector('[id="po-manage-qty-sol-1:new"]');
    expect(headers[columnOf(qty)]).toBe('Qty');
  });

  it('AC-HT2a: with a linked row too, Action holds the Keep / Unlink picker and Qty holds the new row qty box', () => {
    const dialog = renderMulti([newLine('sol-1', 'SO425045'), linkedLine], { 'sol-1': 'prod-A', 'sol-2': 'prod-B' });
    const headers = headerTexts(dialog);
    expect(headers).toContain('Qty');
    expect(headers).toContain('Action');
    const qty = dialog.querySelector('[id="po-manage-qty-sol-1:new"]');
    const action = dialog.querySelector('[id="po-manage-action-sol-2:po-7"]');
    expect(headers[columnOf(qty)]).toBe('Qty');
    expect(headers[columnOf(action)]).toBe('Action');
  });
});
