/**
 * CompareMappingDialog - DO-COMPARE-SIM red tests (AC-CMM-13).
 *
 * Mocked at the service boundary (`../services/autocountPullService`); the real
 * `useCompareMappings` / `useSaveCompareMapping` hooks run over a real QueryClient.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const getCompareMappings = vi.fn();
const saveCompareMapping = vi.fn();
vi.mock('../services/autocountPullService', () => ({
  getCompareMappings: (...a: unknown[]) => getCompareMappings(...a),
  saveCompareMapping: (...a: unknown[]) => saveCompareMapping(...a),
  comparePull: vi.fn(),
}));

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }));
vi.mock('@/lib/toast', () => ({ toast }));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

import { CompareMappingDialog } from './CompareMappingDialog';

const LISTING_COLUMNS = [
  { excel_header: 'Doc No', transform: 'text', field: 'doc_no' },
  { excel_header: 'Item Code', transform: 'text', field: 'item_code' },
  { excel_header: 'Discount', transform: 'percent_text', field: 'discount' },
];
const TRACKING_COLUMNS = [
  { excel_header: 'Doc. No.', transform: 'text', field: 'doc_no' },
  { excel_header: 'Cancel', transform: 'cancel_flag', field: 'cancel' },
];
const MAPPINGS = {
  items: [
    { kind: 'order_listing', sheet_name: 'Master', columns: LISTING_COLUMNS, updated_at: null },
    { kind: 'order_tracking', sheet_name: 'Master', columns: TRACKING_COLUMNS, updated_at: null },
  ],
};

function renderDialog(onOpenChange = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    React.createElement(
      QueryClientProvider,
      { client },
      React.createElement(CompareMappingDialog, { open: true, onOpenChange }),
    ),
  );
  return { ...utils, client, onOpenChange };
}

beforeEach(() => {
  getCompareMappings.mockReset().mockResolvedValue(MAPPINGS);
  saveCompareMapping.mockReset();
  Object.values(toast).forEach((f) => f.mockReset());
});

describe('CompareMappingDialog', () => {
  it('shows the two workbook kinds as tabs and the listing rows by default', async () => {
    renderDialog();
    expect(await screen.findByRole('tab', { name: 'Order Listing' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Order Tracking' })).toBeInTheDocument();
    expect(await screen.findByLabelText('Sheet name')).toHaveValue('Master');
    const headers = screen.getAllByLabelText('Excel column').map((i) => (i as HTMLInputElement).value);
    expect(headers).toEqual(['Doc No', 'Item Code', 'Discount']);
  });

  it('switches to the Order Tracking rows', async () => {
    renderDialog();
    const tab = await screen.findByRole('tab', { name: 'Order Tracking' });
    fireEvent.mouseDown(tab);
    fireEvent.click(tab);
    await waitFor(() =>
      expect(
        screen.getAllByLabelText('Excel column').map((i) => (i as HTMLInputElement).value),
      ).toEqual(['Doc. No.', 'Cancel']),
    );
  });

  it('Add row appends an empty Excel column input', async () => {
    renderDialog();
    await screen.findByLabelText('Sheet name');
    const before = screen.getAllByLabelText('Excel column').length;
    fireEvent.click(screen.getByRole('button', { name: 'Add row' }));
    expect(screen.getAllByLabelText('Excel column')).toHaveLength(before + 1);
  });

  it('Save sends the edited sheet name and the rows for the active kind', async () => {
    saveCompareMapping.mockResolvedValue({ ...MAPPINGS.items[0], sheet_name: 'Sheet Y' });
    renderDialog();
    const sheet = await screen.findByLabelText('Sheet name');
    fireEvent.change(sheet, { target: { value: 'Sheet Y' } });
    const first = screen.getAllByLabelText('Excel column')[0];
    fireEvent.change(first, { target: { value: 'Doc Number' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(saveCompareMapping).toHaveBeenCalledTimes(1));
    const [kind, body] = saveCompareMapping.mock.calls[0];
    expect(kind).toBe('order_listing');
    expect(body.sheet_name).toBe('Sheet Y');
    expect(body.columns[0]).toEqual({ excel_header: 'Doc Number', transform: 'text', field: 'doc_no' });
    expect(body.columns).toHaveLength(3);
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
  });

  it('a failed save shows the extracted message and does not toast success', async () => {
    saveCompareMapping.mockRejectedValue(new Error('Map doc_no and item_code.'));
    renderDialog();
    await screen.findByLabelText('Sheet name');
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Map doc_no and item_code.'));
    expect(toast.success).not.toHaveBeenCalled();
  });
});
