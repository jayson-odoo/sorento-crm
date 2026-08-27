/**
 * "Place on PO" (section G, reworked G2, PLAN-demo-followups-19aug-ladder-v2.md): the
 * candidates table loads from `GET .../po-candidates`, opens already showing the
 * cascade's own preview (`default_take`) per line, lets the take be edited, and confirms
 * by posting the whole allocation in one call (`POST .../place-on-po { allocations }`).
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
const placeOrderInquiryRowOnPoAllocations = vi.fn();

vi.mock('../services/orderInquiryService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/orderInquiryService')>();
  return {
    ...actual,
    getOrderInquiryPoCandidates: (...args: unknown[]) => getOrderInquiryPoCandidates(...args),
    placeOrderInquiryRowOnPoAllocations: (...args: unknown[]) =>
      placeOrderInquiryRowOnPoAllocations(...args),
  };
});

import { LinkDocumentDialog } from './LinkDocumentDialog';

const EARLY: OrderInquiryPoCandidate = {
  kind: 'po',
  po_line_id: 'po-line-early',
  tier: 1,
  location: 'BRW-IB',
  issue_date: '2026-08-01',
  cited: false,
  po_number: 'ZZT-PO-0001',
  supplier_name: 'Dafuyuan',
  expected_date: '2026-09-01',
  qty_ordered: '15',
  qty_received: '0',
  already_tagged: '0',
  remaining: '15',
  covers: false,
  recommended: false,
  default_take: '15',
  claims: [],
};

const LATER: OrderInquiryPoCandidate = {
  kind: 'po',
  po_line_id: 'po-line-later',
  tier: 3,
  location: 'BRW',
  issue_date: '2026-08-05',
  cited: false,
  po_number: 'ZZT-PO-0002',
  supplier_name: 'Another Factory',
  expected_date: '2026-09-15',
  qty_ordered: '20',
  qty_received: '0',
  already_tagged: '0',
  remaining: '20',
  covers: true,
  recommended: false,
  default_take: '10',
  claims: [],
};

function renderDialog(node: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

const onDone = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  getOrderInquiryPoCandidates.mockReset();
  placeOrderInquiryRowOnPoAllocations.mockReset();
});

describe('LinkDocumentDialog: loading, empty and error states', () => {
  it('shows a skeleton while the candidates are loading', () => {
    getOrderInquiryPoCandidates.mockReturnValue(new Promise(() => {}));

    renderDialog(
      <LinkDocumentDialog rowId="row-1" itemCode="BASIN-001" qty="25" onDone={onDone} />,
    );

    expect(screen.queryByTestId('po-candidates-table')).not.toBeInTheDocument();
    expect(screen.queryByTestId('po-candidates-empty')).not.toBeInTheDocument();
  });

  it('names an empty result rather than showing a blank table', async () => {
    getOrderInquiryPoCandidates.mockResolvedValue([]);

    renderDialog(
      <LinkDocumentDialog rowId="row-1" itemCode="BASIN-001" qty="25" onDone={onDone} />,
    );

    expect(await screen.findByTestId('po-candidates-empty')).toHaveTextContent(
      'No outstanding purchase order line or SPO allocation holds this item.',
    );
    expect(screen.getByRole('button', { name: 'Link' })).toBeDisabled();
  });

  it('shows the error rather than an empty table when the candidates fail to load', async () => {
    getOrderInquiryPoCandidates.mockRejectedValue(new Error('Failed to load candidate lines'));

    renderDialog(
      <LinkDocumentDialog rowId="row-1" itemCode="BASIN-001" qty="25" onDone={onDone} />,
    );

    expect(await screen.findByText('Could not load candidate lines')).toBeInTheDocument();
    expect(screen.getByText('Failed to load candidate lines')).toBeInTheDocument();
  });
});

describe('LinkDocumentDialog: the cascade preview', () => {
  it('opens with each line pre-filled at its own cascade take', async () => {
    getOrderInquiryPoCandidates.mockResolvedValue([EARLY, LATER]);

    renderDialog(
      <LinkDocumentDialog rowId="row-1" itemCode="BASIN-001" qty="25" onDone={onDone} />,
    );

    await screen.findByTestId('po-candidates-table');
    const earlyInput = screen.getByLabelText('Take off ZZT-PO-0001') as HTMLInputElement;
    const laterInput = screen.getByLabelText('Take off ZZT-PO-0002') as HTMLInputElement;
    expect(earlyInput.value).toBe('15');
    expect(laterInput.value).toBe('10');
    expect(screen.getByTestId('po-allocation-summary')).toHaveTextContent('25 of 25 linked');
    expect(screen.getByRole('button', { name: 'Link' })).toBeEnabled();
  });

  it('names the cascade take on the candidate the pass would use', async () => {
    getOrderInquiryPoCandidates.mockResolvedValue([EARLY, LATER]);

    renderDialog(
      <LinkDocumentDialog rowId="row-1" itemCode="BASIN-001" qty="25" onDone={onDone} />,
    );

    const early = await screen.findByTestId('po-candidate-po:po-line-early');
    expect(early).toHaveTextContent('Cascade take 15');
  });

  it('reports the leftover as still demand when the cascade only partly covers the row', async () => {
    getOrderInquiryPoCandidates.mockResolvedValue([EARLY]);

    renderDialog(
      <LinkDocumentDialog rowId="row-1" itemCode="BASIN-001" qty="25" onDone={onDone} />,
    );

    await screen.findByTestId('po-candidates-table');
    expect(screen.getByTestId('po-allocation-summary')).toHaveTextContent(
      '15 of 25 linked - 10 stays demand',
    );
    expect(screen.getByRole('button', { name: 'Link' })).toBeEnabled();
  });
});

describe('LinkDocumentDialog: editing the take', () => {
  it('refuses to confirm when a line is edited past its own remaining balance', async () => {
    getOrderInquiryPoCandidates.mockResolvedValue([EARLY]);

    renderDialog(
      <LinkDocumentDialog rowId="row-1" itemCode="BASIN-001" qty="25" onDone={onDone} />,
    );

    const input = await screen.findByLabelText('Take off ZZT-PO-0001');
    fireEvent.change(input, { target: { value: '20' } });

    expect(screen.getByText("A line's take is more than it has left")).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Link' })).toBeDisabled();
  });

  it('refuses to confirm when the total taken is more than the row needs', async () => {
    getOrderInquiryPoCandidates.mockResolvedValue([EARLY, LATER]);

    renderDialog(
      <LinkDocumentDialog rowId="row-1" itemCode="BASIN-001" qty="25" onDone={onDone} />,
    );

    const laterInput = await screen.findByLabelText('Take off ZZT-PO-0002');
    fireEvent.change(laterInput, { target: { value: '20' } });

    expect(screen.getByText('10 more than this row needs')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Link' })).toBeDisabled();
  });

  it('refuses to confirm with nothing taken at all', async () => {
    getOrderInquiryPoCandidates.mockResolvedValue([EARLY]);

    renderDialog(
      <LinkDocumentDialog rowId="row-1" itemCode="BASIN-001" qty="25" onDone={onDone} />,
    );

    const input = await screen.findByLabelText('Take off ZZT-PO-0001');
    fireEvent.change(input, { target: { value: '0' } });

    expect(screen.getByRole('button', { name: 'Link' })).toBeDisabled();
  });
});

describe('LinkDocumentDialog: confirming', () => {
  it('posts the whole allocation in one call and closes on success', async () => {
    getOrderInquiryPoCandidates.mockResolvedValue([EARLY, LATER]);
    placeOrderInquiryRowOnPoAllocations.mockResolvedValue({ id: 'row-1', state: 'placed' });

    renderDialog(
      <LinkDocumentDialog rowId="row-1" itemCode="BASIN-001" qty="25" onDone={onDone} />,
    );

    await screen.findByTestId('po-candidates-table');
    fireEvent.click(screen.getByRole('button', { name: 'Link' }));

    await waitFor(() =>
      expect(placeOrderInquiryRowOnPoAllocations).toHaveBeenCalledWith('row-1', [
        { po_line_id: 'po-line-early', qty: '15' },
        { po_line_id: 'po-line-later', qty: '10' },
      ]),
    );
    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  it('posts a hand-edited take rather than the cascade default', async () => {
    getOrderInquiryPoCandidates.mockResolvedValue([EARLY]);
    placeOrderInquiryRowOnPoAllocations.mockResolvedValue({ id: 'row-1', state: 'placed' });

    renderDialog(
      <LinkDocumentDialog rowId="row-1" itemCode="BASIN-001" qty="25" onDone={onDone} />,
    );

    const input = await screen.findByLabelText('Take off ZZT-PO-0001');
    fireEvent.change(input, { target: { value: '12' } });
    fireEvent.click(screen.getByRole('button', { name: 'Link' }));

    await waitFor(() =>
      expect(placeOrderInquiryRowOnPoAllocations).toHaveBeenCalledWith('row-1', [
        { po_line_id: 'po-line-early', qty: '12' },
      ]),
    );
  });

  it('drops a line cleared to zero from the posted allocation', async () => {
    getOrderInquiryPoCandidates.mockResolvedValue([EARLY, LATER]);
    placeOrderInquiryRowOnPoAllocations.mockResolvedValue({ id: 'row-1', state: 'placed' });

    renderDialog(
      <LinkDocumentDialog rowId="row-1" itemCode="BASIN-001" qty="25" onDone={onDone} />,
    );

    const laterInput = await screen.findByLabelText('Take off ZZT-PO-0002');
    fireEvent.change(laterInput, { target: { value: '0' } });
    fireEvent.click(screen.getByRole('button', { name: 'Link' }));

    await waitFor(() =>
      expect(placeOrderInquiryRowOnPoAllocations).toHaveBeenCalledWith('row-1', [
        { po_line_id: 'po-line-early', qty: '15' },
      ]),
    );
  });

  it('closes without placing anything on Cancel', async () => {
    getOrderInquiryPoCandidates.mockResolvedValue([EARLY]);

    renderDialog(
      <LinkDocumentDialog rowId="row-1" itemCode="BASIN-001" qty="25" onDone={onDone} />,
    );

    await screen.findByTestId('po-candidates-table');
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(onDone).toHaveBeenCalled();
    expect(placeOrderInquiryRowOnPoAllocations).not.toHaveBeenCalled();
  });
});

describe('LinkDocumentDialog: the candidate expand (section G, unchanged by G2)', () => {
  it('the chevron toggles the nested line/claims panel, collapsed by default', async () => {
    getOrderInquiryPoCandidates.mockResolvedValue([EARLY]);

    renderDialog(
      <LinkDocumentDialog rowId="row-1" itemCode="BASIN-001" qty="25" onDone={onDone} />,
    );

    await screen.findByTestId('po-candidates-table');
    expect(screen.queryByTestId('po-candidate-expand-po:po-line-early')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Expand' }));
    expect(screen.getByTestId('po-candidate-expand-po:po-line-early')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Collapse' }));
    expect(screen.queryByTestId('po-candidate-expand-po:po-line-early')).not.toBeInTheDocument();
  });

  it('names an empty result rather than showing a blank claims table', async () => {
    getOrderInquiryPoCandidates.mockResolvedValue([EARLY]);

    renderDialog(
      <LinkDocumentDialog rowId="row-1" itemCode="BASIN-001" qty="25" onDone={onDone} />,
    );

    await screen.findByTestId('po-candidates-table');
    fireEvent.click(screen.getByRole('button', { name: 'Expand' }));

    expect(
      screen.getByText('No other row is linked to this line yet.'),
    ).toBeInTheDocument();
  });

  it('lists every other row already tagged to the line, with the unit price in currency', async () => {
    const priced: OrderInquiryPoCandidate = {
      ...EARLY,
      unit_cost: '12.75',
      currency: 'MYR',
      claims: [
        { so_number: 'SO2026001', item_code: 'BASIN-001', qty: '20', placed_date: '2026-08-01' },
        { so_number: 'SO2026002', item_code: 'BASIN-001', qty: '15', placed_date: '2026-08-05' },
      ],
    };
    getOrderInquiryPoCandidates.mockResolvedValue([priced]);

    renderDialog(
      <LinkDocumentDialog rowId="row-1" itemCode="BASIN-001" qty="10" onDone={onDone} />,
    );

    await screen.findByTestId('po-candidates-table');
    fireEvent.click(screen.getByRole('button', { name: 'Expand' }));

    const panel = screen.getByTestId('po-candidate-expand-po:po-line-early');
    expect(panel).toHaveTextContent('MYR 12.75');
    expect(panel).toHaveTextContent('SO2026001');
    expect(panel).toHaveTextContent('SO2026002');
    expect(panel).toHaveTextContent('20');
    expect(panel).toHaveTextContent('15');
  });

  it('names no price on file when the line carries none', async () => {
    getOrderInquiryPoCandidates.mockResolvedValue([EARLY]);

    renderDialog(
      <LinkDocumentDialog rowId="row-1" itemCode="BASIN-001" qty="25" onDone={onDone} />,
    );

    await screen.findByTestId('po-candidates-table');
    fireEvent.click(screen.getByRole('button', { name: 'Expand' }));

    expect(screen.getByText('No price on file')).toBeInTheDocument();
  });
});

/**
 * The LINK HORIZON in the dialog (AC-LH3, `PLAN-scm-oi-handshake.md` section 11).
 *
 * The same date the page's presses run to, shown at the top so a hand-made link is made
 * against a known horizon rather than a guessed one - and a notice on a row that falls
 * past it. Never a refusal: this dialog is override and audit, so a person who has looked
 * at the line may still take it.
 */
describe('LinkDocumentDialog: the link horizon', () => {
  it('AC-LH3: shows the horizon, and flags a row due after it while still allowing the take', async () => {
    getOrderInquiryPoCandidates.mockResolvedValue([EARLY]);

    renderDialog(
      <LinkDocumentDialog
        rowId="row-1"
        itemCode="BASIN-001"
        qty="15"
        deliveryDate="2030-01-01"
        linkUpTo="2026-12-31"
        onDone={onDone}
      />,
    );

    // The candidates first: the horizon renders straight away, so asserting on it alone
    // would pass on a dialog that never loaded a line.
    expect(await screen.findByTestId('po-candidates-table')).toBeInTheDocument();
    expect(screen.getByTestId('link-dialog-horizon')).toHaveTextContent(
      'Link up to 31/12/2026',
    );
    expect(screen.getByTestId('link-dialog-due-after')).toHaveTextContent(
      'Due after 31/12/2026',
    );
    expect(screen.getByRole('button', { name: 'Link' })).toBeEnabled();
  });

  it('AC-LH4: a row with no delivery date is inside the horizon, so no notice', async () => {
    getOrderInquiryPoCandidates.mockResolvedValue([EARLY]);

    renderDialog(
      <LinkDocumentDialog
        rowId="row-1"
        itemCode="BASIN-001"
        qty="15"
        deliveryDate={null}
        linkUpTo="2026-12-31"
        onDone={onDone}
      />,
    );

    await screen.findByTestId('po-candidates-table');
    expect(screen.getByTestId('link-dialog-horizon')).toBeInTheDocument();
    expect(screen.queryByTestId('link-dialog-due-after')).toBeNull();
  });

  it('says nothing about a horizon when none is in force', async () => {
    getOrderInquiryPoCandidates.mockResolvedValue([EARLY]);

    renderDialog(
      <LinkDocumentDialog rowId="row-1" itemCode="BASIN-001" qty="15" onDone={onDone} />,
    );

    await screen.findByTestId('po-candidates-table');
    expect(screen.queryByTestId('link-dialog-horizon')).toBeNull();
  });
});
