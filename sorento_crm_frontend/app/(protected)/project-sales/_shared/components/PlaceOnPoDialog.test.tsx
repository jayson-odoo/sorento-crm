/**
 * "Place on PO" (section G, PLAN-demo-followups-19aug-ladder-v2.md): the candidates table
 * loads from `GET .../po-candidates`, offers only a covering line as a valid choice - a
 * non-covering one is shown, never hidden, disabled and naming its shortfall - and defaults
 * the selection to the server's own `recommended` flag. Placing posts the chosen
 * `po_line_id` and closes on success.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { OrderInquiryPoCandidate } from '../types/orderInquiry.types';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const getOrderInquiryPoCandidates = vi.fn();
const placeOrderInquiryRowOnPo = vi.fn();

vi.mock('../services/orderInquiryService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/orderInquiryService')>();
  return {
    ...actual,
    getOrderInquiryPoCandidates: (...args: unknown[]) => getOrderInquiryPoCandidates(...args),
    placeOrderInquiryRowOnPo: (...args: unknown[]) => placeOrderInquiryRowOnPo(...args),
  };
});

import { PlaceOnPoDialog } from './PlaceOnPoDialog';

const COVERING: OrderInquiryPoCandidate = {
  po_line_id: 'po-line-covering',
  po_number: 'ZZT-PO-0001',
  supplier_name: 'Dafuyuan',
  expected_date: '2026-09-15',
  qty_ordered: '50',
  qty_received: '0',
  already_tagged: '0',
  remaining: '50',
  covers: true,
  recommended: true,
};

const SHORT: OrderInquiryPoCandidate = {
  po_line_id: 'po-line-short',
  po_number: 'ZZT-PO-0002',
  supplier_name: 'Another Factory',
  expected_date: '2026-09-01',
  qty_ordered: '10',
  qty_received: '0',
  already_tagged: '0',
  remaining: '10',
  covers: false,
  recommended: false,
};

function renderDialog(node: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

const onDone = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  getOrderInquiryPoCandidates.mockReset();
  placeOrderInquiryRowOnPo.mockReset();
});

describe('PlaceOnPoDialog: loading, empty and error states', () => {
  it('shows a skeleton while the candidates are loading', () => {
    getOrderInquiryPoCandidates.mockReturnValue(new Promise(() => {}));

    renderDialog(
      <PlaceOnPoDialog rowId="row-1" itemCode="BASIN-001" qty="30" onDone={onDone} />,
    );

    expect(screen.queryByTestId('po-candidates-table')).not.toBeInTheDocument();
    expect(screen.queryByTestId('po-candidates-empty')).not.toBeInTheDocument();
  });

  it('names an empty result rather than showing a blank table', async () => {
    getOrderInquiryPoCandidates.mockResolvedValue([]);

    renderDialog(
      <PlaceOnPoDialog rowId="row-1" itemCode="BASIN-001" qty="30" onDone={onDone} />,
    );

    expect(await screen.findByTestId('po-candidates-empty')).toHaveTextContent(
      'No outstanding purchase order line holds this item.',
    );
    expect(screen.getByRole('button', { name: 'Place on PO' })).toBeDisabled();
  });

  it('shows the error rather than an empty table when the candidates fail to load', async () => {
    getOrderInquiryPoCandidates.mockRejectedValue(new Error('Failed to load purchase order lines'));

    renderDialog(
      <PlaceOnPoDialog rowId="row-1" itemCode="BASIN-001" qty="30" onDone={onDone} />,
    );

    expect(await screen.findByText('Could not load purchase order lines')).toBeInTheDocument();
    expect(screen.getByText('Failed to load purchase order lines')).toBeInTheDocument();
  });
});

describe('PlaceOnPoDialog: candidates and the recommendation', () => {
  it('opens on the recommended candidate, valid to place immediately', async () => {
    getOrderInquiryPoCandidates.mockResolvedValue([SHORT, COVERING]);

    renderDialog(
      <PlaceOnPoDialog rowId="row-1" itemCode="BASIN-001" qty="30" onDone={onDone} />,
    );

    await screen.findByTestId('po-candidates-table');
    const covering = screen.getByTestId('po-candidate-po-line-covering');
    expect(covering.querySelector('input[type="radio"]')).toBeChecked();
    expect(screen.getByRole('button', { name: 'Place on PO' })).toBeEnabled();
  });

  it('disables a non-covering candidate and names its shortfall, never hiding it', async () => {
    getOrderInquiryPoCandidates.mockResolvedValue([SHORT, COVERING]);

    renderDialog(
      <PlaceOnPoDialog rowId="row-1" itemCode="BASIN-001" qty="30" onDone={onDone} />,
    );

    const shortRow = await screen.findByTestId('po-candidate-po-line-short');
    expect(shortRow.querySelector('input[type="radio"]')).toBeDisabled();
    expect(screen.getByTestId('po-candidate-shortfall-po-line-short')).toHaveTextContent(
      '20 short',
    );
  });

  it('cannot be placed on a non-covering candidate even if selected', async () => {
    getOrderInquiryPoCandidates.mockResolvedValue([SHORT]);

    renderDialog(
      <PlaceOnPoDialog rowId="row-1" itemCode="BASIN-001" qty="30" onDone={onDone} />,
    );

    await screen.findByTestId('po-candidates-table');
    expect(screen.getByRole('button', { name: 'Place on PO' })).toBeDisabled();
    expect(placeOrderInquiryRowOnPo).not.toHaveBeenCalled();
  });
});

describe('PlaceOnPoDialog: placing', () => {
  it('posts the chosen po_line_id and closes on success', async () => {
    getOrderInquiryPoCandidates.mockResolvedValue([SHORT, COVERING]);
    placeOrderInquiryRowOnPo.mockResolvedValue({ id: 'row-1', state: 'placed' });

    renderDialog(
      <PlaceOnPoDialog rowId="row-1" itemCode="BASIN-001" qty="30" onDone={onDone} />,
    );

    await screen.findByTestId('po-candidates-table');
    fireEvent.click(screen.getByRole('button', { name: 'Place on PO' }));

    await waitFor(() =>
      expect(placeOrderInquiryRowOnPo).toHaveBeenCalledWith('row-1', 'po-line-covering'),
    );
    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  it('places on a hand-picked candidate rather than the recommended one', async () => {
    // Both cover the row's need, so neither is disabled - the server named only ONE of
    // them `recommended`, and the dialog must still let the other be chosen by hand.
    const alsoCovers: OrderInquiryPoCandidate = {
      ...SHORT,
      po_line_id: 'po-line-also-covers',
      remaining: '50',
      covers: true,
      recommended: false,
    };
    getOrderInquiryPoCandidates.mockResolvedValue([alsoCovers, COVERING]);
    placeOrderInquiryRowOnPo.mockResolvedValue({ id: 'row-1', state: 'placed' });

    renderDialog(
      <PlaceOnPoDialog rowId="row-1" itemCode="BASIN-001" qty="30" onDone={onDone} />,
    );

    await screen.findByTestId('po-candidates-table');
    expect(screen.getByTestId('po-candidate-po-line-covering').querySelector('input')).toBeChecked();
    const handPicked = screen
      .getByTestId('po-candidate-po-line-also-covers')
      .querySelector('input[type="radio"]') as HTMLInputElement;
    fireEvent.click(handPicked);
    fireEvent.click(screen.getByRole('button', { name: 'Place on PO' }));

    await waitFor(() =>
      expect(placeOrderInquiryRowOnPo).toHaveBeenCalledWith('row-1', 'po-line-also-covers'),
    );
  });

  it('closes without placing anything on Cancel', async () => {
    getOrderInquiryPoCandidates.mockResolvedValue([COVERING]);

    renderDialog(
      <PlaceOnPoDialog rowId="row-1" itemCode="BASIN-001" qty="30" onDone={onDone} />,
    );

    await screen.findByTestId('po-candidates-table');
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(onDone).toHaveBeenCalled();
    expect(placeOrderInquiryRowOnPo).not.toHaveBeenCalled();
  });
});
