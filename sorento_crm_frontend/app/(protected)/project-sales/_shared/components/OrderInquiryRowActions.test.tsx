/**
 * The row action for "Link PO" (section G): a raised ORDER/RESERVE & ORDER row offers
 * Link PO; a placed row offers Unlink; every other row (already actioned, cancelled,
 * or a verb this never applies to) renders nothing.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({
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
  it('offers Link PO for a raised ORDER row', () => {
    renderActions(
      <OrderInquiryRowActions rowId="row-1" verb="ORDER" state="raised" qty="10" />,
    );

    expect(screen.getByRole('button', { name: /Link PO/ })).toBeInTheDocument();
  });

  it('offers Link PO for a raised RESERVE_AND_ORDER row too', () => {
    renderActions(
      <OrderInquiryRowActions rowId="row-1" verb="RESERVE_AND_ORDER" state="raised" qty="10" />,
    );

    expect(screen.getByRole('button', { name: /Link PO/ })).toBeInTheDocument();
  });

  it('opens the candidates dialog on click', () => {
    renderActions(
      <OrderInquiryRowActions rowId="row-1" verb="ORDER" state="raised" qty="10" itemCode="BASIN-001" />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Link PO/ }));

    expect(screen.getByText('Link to a document')).toBeInTheDocument();
    expect(getOrderInquiryPoCandidates).toHaveBeenCalledWith('row-1');
  });
});

describe('OrderInquiryRowActions: rows Link PO does not apply to', () => {
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

  it('renders no Link PO action when the row carries hasLinkCandidate=false', () => {
    // The backend's own `has_link_candidate` says nothing is left to tag - a "Link PO"
    // that opens on an empty dialog reads as a bug, not an empty state, so the row offers
    // nothing at all rather than an offer with nothing behind it.
    renderActions(
      <OrderInquiryRowActions
        rowId="row-1"
        verb="ORDER"
        state="raised"
        qty="10"
        hasLinkCandidate={false}
      />,
    );

    expect(screen.queryByRole('button', { name: /Link PO/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('offers Link PO when hasLinkCandidate is left unstated (default true)', () => {
    // An omitted flag never HIDES the offer - only an explicit false does.
    renderActions(<OrderInquiryRowActions rowId="row-1" verb="ORDER" state="raised" qty="10" />);

    expect(screen.getByRole('button', { name: /Link PO/ })).toBeInTheDocument();
  });

  it('offers Link PO when hasLinkCandidate is explicitly true', () => {
    renderActions(
      <OrderInquiryRowActions
        rowId="row-1"
        verb="ORDER"
        state="raised"
        qty="10"
        hasLinkCandidate
      />,
    );

    expect(screen.getByRole('button', { name: /Link PO/ })).toBeInTheDocument();
  });
});

describe('OrderInquiryRowActions: a placed row', () => {
  it('offers Unlink instead of Link PO', () => {
    renderActions(
      <OrderInquiryRowActions
        rowId="row-1"
        verb="ORDER"
        state="placed"
        qty="10"
        poLabel="ZZT-PO-0001"
      />,
    );

    expect(screen.getByRole('button', { name: /Unlink/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Link PO/ })).not.toBeInTheDocument();
  });

  it('opens the confirm naming the linked purchase order', () => {
    renderActions(
      <OrderInquiryRowActions
        rowId="row-1"
        verb="ORDER"
        state="placed"
        qty="10"
        poLabel="ZZT-PO-0001"
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Unlink/ }));

    expect(
      screen.getByText(
        'Remove the link to ZZT-PO-0001? That quantity goes back to demand, and the next reorder suggestion counts it again.',
      ),
    ).toBeInTheDocument();
  });
});

describe('OrderInquiryRowActions: the ORDER BACK row (part 2 section 4b)', () => {
  it('offers Link when the backend says it has a candidate, even with no purchase order', () => {
    // `has_link_candidate` counts SPO allocations for this verb, which is the whole point
    // of it: a flag that counted purchase orders alone hid Link on the one row the
    // feature was built for.
    renderActions(
      <OrderInquiryRowActions
        rowId="row-1"
        verb="ORDER_BACK"
        state="raised"
        qty="10"
        hasLinkCandidate
      />,
    );

    expect(screen.getByRole('button', { name: /Link PO/ })).toBeInTheDocument();
  });

  it('renders nothing when the row has nowhere at all to link', () => {
    renderActions(
      <OrderInquiryRowActions
        rowId="row-1"
        verb="ORDER_BACK"
        state="raised"
        qty="10"
        hasLinkCandidate={false}
      />,
    );

    expect(screen.queryByRole('button', { name: /Link/ })).not.toBeInTheDocument();
  });
});

describe('OrderInquiryRowActions: a partly linked row', () => {
  it('offers BOTH Link and Unlink - it has quantity left and links to give back', () => {
    renderActions(
      <OrderInquiryRowActions
        rowId="row-1"
        verb="ORDER"
        state="partly_linked"
        qty="8"
        linkedQty="5"
        linkCount={1}
        poLabel="ZZT-PO-0001"
      />,
    );

    expect(screen.getByRole('button', { name: /Link PO/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Unlink/ })).toBeInTheDocument();
  });

  it('names the COUNT when a whole-row Unlink would take more than one link', () => {
    renderActions(
      <OrderInquiryRowActions
        rowId="row-1"
        verb="ORDER"
        state="placed"
        qty="8"
        linkCount={2}
        poLabel="ZZT-PO-0001"
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Unlink/ }));

    expect(
      screen.getByText(
        'Remove all 2 links on this row? Those quantities go back to demand, and the next reorder suggestion counts them again.',
      ),
    ).toBeInTheDocument();
  });
});
