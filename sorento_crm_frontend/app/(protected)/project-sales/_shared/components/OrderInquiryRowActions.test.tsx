/**
 * The row action for "Place on PO" (section G): a raised ORDER/RESERVE & ORDER row offers
 * Place on PO; a placed row offers Unplace; every other row (already actioned, cancelled,
 * or a verb this never applies to) renders nothing.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const getOrderInquiryPoCandidates = vi.fn();

vi.mock('../services/orderInquiryService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/orderInquiryService')>();
  return {
    ...actual,
    getOrderInquiryPoCandidates: (...args: unknown[]) => getOrderInquiryPoCandidates(...args),
  };
});

import { OrderInquiryRowActions } from './OrderInquiryRowActions';

function renderActions(node: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  getOrderInquiryPoCandidates.mockResolvedValue([]);
});

describe('OrderInquiryRowActions: placeable raised rows', () => {
  it('offers Place on PO for a raised ORDER row', () => {
    renderActions(
      <OrderInquiryRowActions rowId="row-1" verb="ORDER" state="raised" qty="10" />,
    );

    expect(screen.getByRole('button', { name: /Place on PO/ })).toBeInTheDocument();
  });

  it('offers Place on PO for a raised RESERVE_AND_ORDER row too', () => {
    renderActions(
      <OrderInquiryRowActions rowId="row-1" verb="RESERVE_AND_ORDER" state="raised" qty="10" />,
    );

    expect(screen.getByRole('button', { name: /Place on PO/ })).toBeInTheDocument();
  });

  it('opens the candidates dialog on click', () => {
    renderActions(
      <OrderInquiryRowActions rowId="row-1" verb="ORDER" state="raised" qty="10" itemCode="BASIN-001" />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Place on PO/ }));

    expect(screen.getByText('Place on a purchase order')).toBeInTheDocument();
    expect(getOrderInquiryPoCandidates).toHaveBeenCalledWith('row-1');
  });
});

describe('OrderInquiryRowActions: rows Place on PO does not apply to', () => {
  it('renders nothing for a raised row of a non-placeable verb', () => {
    renderActions(
      <OrderInquiryRowActions rowId="row-1" verb="ALREADY_INBOUND" state="raised" qty="10" />,
    );

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('renders nothing for an actioned ORDER row', () => {
    renderActions(
      <OrderInquiryRowActions rowId="row-1" verb="ORDER" state="actioned" qty="10" />,
    );

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('renders nothing for a cancelled row', () => {
    renderActions(
      <OrderInquiryRowActions rowId="row-1" verb="ORDER" state="cancelled" qty="10" />,
    );

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('renders nothing for a BORROW_SHORTFALL row, even though it still costs money', () => {
    renderActions(
      <OrderInquiryRowActions rowId="row-1" verb="BORROW_SHORTFALL" state="raised" qty="10" />,
    );

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('renders no Place on PO action when the row carries hasOpenPoLine=false', () => {
    // The backend's own `has_open_po_line` says nothing is left to tag - a "Place on PO"
    // that opens on an empty dialog reads as a bug, not an empty state, so the row offers
    // nothing at all rather than an offer with nothing behind it.
    renderActions(
      <OrderInquiryRowActions
        rowId="row-1"
        verb="ORDER"
        state="raised"
        qty="10"
        hasOpenPoLine={false}
      />,
    );

    expect(screen.queryByRole('button', { name: /Place on PO/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('offers Place on PO when hasOpenPoLine is left unstated (default true)', () => {
    // An omitted flag never HIDES the offer - only an explicit false does.
    renderActions(<OrderInquiryRowActions rowId="row-1" verb="ORDER" state="raised" qty="10" />);

    expect(screen.getByRole('button', { name: /Place on PO/ })).toBeInTheDocument();
  });

  it('offers Place on PO when hasOpenPoLine is explicitly true', () => {
    renderActions(
      <OrderInquiryRowActions
        rowId="row-1"
        verb="ORDER"
        state="raised"
        qty="10"
        hasOpenPoLine
      />,
    );

    expect(screen.getByRole('button', { name: /Place on PO/ })).toBeInTheDocument();
  });
});

describe('OrderInquiryRowActions: a placed row', () => {
  it('offers Unplace instead of Place on PO', () => {
    renderActions(
      <OrderInquiryRowActions
        rowId="row-1"
        verb="ORDER"
        state="placed"
        qty="10"
        poLabel="ZZT-PO-0001"
      />,
    );

    expect(screen.getByRole('button', { name: /Unplace/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Place on PO/ })).not.toBeInTheDocument();
  });

  it('opens the confirm naming the tagged purchase order', () => {
    renderActions(
      <OrderInquiryRowActions
        rowId="row-1"
        verb="ORDER"
        state="placed"
        qty="10"
        poLabel="ZZT-PO-0001"
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Unplace/ }));

    expect(
      screen.getByText(
        'Remove the tag to ZZT-PO-0001? This row goes back to raised, and the next reorder suggestion counts it again.',
      ),
    ).toBeInTheDocument();
  });
});
