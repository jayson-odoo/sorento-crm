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
} from '../types/stockDebtSnapshot.types';

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
    options?: { value: string; label: string }[];
    placeholder?: string;
    truncateTriggerLabel?: boolean;
  }) => (
    <select
      id={props.id}
      data-truncate={props.truncateTriggerLabel ? 'true' : 'false'}
      value={props.value ?? ''}
      onChange={(event) => props.onChange(event.target.value)}
    >
      <option value="">{props.placeholder ?? ''}</option>
      {(props.options ?? []).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

const linkPoLines = vi.fn();
const relocatePoLine = vi.fn();
const resumePoLink = vi.fn();
vi.mock('../services/stockDebtSnapshotService', () => ({
  linkPoLines: (...args: unknown[]) => linkPoLines(...args),
  unlinkPoLines: vi.fn(),
  relinkPoLines: vi.fn(),
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
  },
  {
    po_line_id: 'po-7', po_number: '202610-S0007', po_line_no: 1, location_code: 'MWH-BB',
    delivery_date: '2026-11-20', po_qty: 120, free_qty: 120, supplier_name: 'Supplier A',
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

function renderDialog(lines = [soLine({})]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onClose = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <PoLinkDialog
        mode="link"
        snapshotId="snap"
        rowId="row"
        lines={lines}
        allLines={lines}
        capabilities={CAPS}
        poLines={PO_LINES}
        onClose={onClose}
      />
    </QueryClientProvider>,
  );
  return { dialog: screen.getByTestId('po-link-dialog'), onClose };
}

beforeEach(() => {
  linkPoLines.mockReset();
  relocatePoLine.mockReset();
  resumePoLink.mockReset();
});

describe('Link to PO popup', () => {
  it('one ticked row per line with Location, Delivery date, Outstanding, PO, PO qty, Free and Qty', () => {
    const { dialog } = renderDialog();
    const headers = within(dialog).getAllByRole('columnheader').map((cell) => cell.textContent);
    expect(headers.slice(1)).toEqual([
      'Sales order', 'Line', 'Location', 'Delivery date', 'Outstanding', 'PO', 'PO qty', 'Free', 'Qty',
    ]);
    expect(dialog).toHaveTextContent('18/11/2026');
    expect(within(dialog).getByRole('checkbox', { name: /select so425045 line 140/i })).toBeChecked();
    expect(dialog).toHaveTextContent('1 of 1 lines');
  });

  it('the PO picker truncates its label so the clear button never overlaps it (375 px)', () => {
    const { dialog } = renderDialog();
    expect(dialog.querySelector('#po-link-po-sol-1')).toHaveAttribute('data-truncate', 'true');
  });

  it('the PO picker names the line by the number the server gives (AutoCount line number)', () => {
    const { dialog } = renderDialog();
    const options = [...(dialog.querySelector('#po-link-po-sol-1') as HTMLSelectElement).options];
    expect(options.map((o) => o.textContent)).toContain('202609-S0029 · line 3 · HQ · 380 free');
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
    const lines = [soLine({}), soLine({ sales_order_line_id: 'sol-2', so_number: 'SO425046', line_no: 3, open_qty: 300 })];
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
