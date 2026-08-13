/**
 * FormDetailTabsWithRevisions - the office Revisions tab gating rule (round 6,
 * UAC H2 / H7, source doc comment above the component).
 *
 * The tab shows when the TYPE is enabled (regardless of lineage - it carries
 * RevisionsSection's own empty state), OR when the type is disabled but the
 * record already has a lineage (`revision_no > 0`). The kill switch only stops
 * new revisions being CREATED; it must never hide history that already
 * happened, because the portal keeps showing the contact that same history
 * (UAC H6's invariant). While the enabled-map query is loading or errors, the
 * tab is absent rather than guessing.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const useRevisionEnabledMapMock = vi.fn();
vi.mock('./useRevisionEnabledMap', () => ({
  useRevisionEnabledMap: () => useRevisionEnabledMapMock(),
}));

const useStockInquiryMock = vi.fn();
vi.mock(
  '@/app/(protected)/procurement-management/stock-inquiries/hooks/useStockInquiries',
  () => ({ useStockInquiry: (...a: unknown[]) => useStockInquiryMock(...a) }),
);

const usePurchaseRequestMock = vi.fn();
vi.mock(
  '@/app/(protected)/procurement-management/purchase-requests/hooks/usePurchaseRequests',
  () => ({ usePurchaseRequest: (...a: unknown[]) => usePurchaseRequestMock(...a) }),
);

// The tab's own body is irrelevant to the gating rule under test - stub it so
// this file exercises FormDetailTabsWithRevisions in isolation.
vi.mock('./FormRevisionsTab', () => ({
  __esModule: true,
  default: () => <div data-testid="form-revisions-tab" />,
}));

import FormDetailTabsWithRevisions from './FormDetailTabsWithRevisions';
import type { FormDetailExtraTab } from './FormDetailWithSLATabs';
import type { FormRevisionsKind } from './FormRevisionsTab';

function renderTabs(props: {
  revisionsKind?: FormRevisionsKind;
  sourceEntityId?: string;
  extraTabs?: FormDetailExtraTab[];
} = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <FormDetailTabsWithRevisions
        sourceEntityType="stock_inquiry"
        sourceEntityId={props.sourceEntityId ?? 'si-1'}
        revisionsKind={props.revisionsKind ?? 'stock_inquiry'}
        extraTabs={props.extraTabs}
      >
        <div>Details content</div>
      </FormDetailTabsWithRevisions>
    </QueryClientProvider>,
  );
}

function revisionsTab() {
  return screen.queryByRole('tab', { name: 'Revisions' });
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  useStockInquiryMock.mockReturnValue({ data: undefined, isLoading: false });
  usePurchaseRequestMock.mockReturnValue({ data: undefined, isLoading: false });
});

describe('FormDetailTabsWithRevisions - office visibility rule', () => {
  it('shows the Revisions tab when the type is enabled, even with no lineage at all', () => {
    useRevisionEnabledMapMock.mockReturnValue({ data: { stock_inquiry: true } });
    renderTabs();

    expect(revisionsTab()).toBeInTheDocument();
    // The enabled case never needs to know whether this record has history -
    // both probe hooks stay switched off (null id).
    expect(useStockInquiryMock).toHaveBeenCalledWith(null);
  });

  it('keeps the Revisions tab when the type is disabled but the record already has a lineage', () => {
    useRevisionEnabledMapMock.mockReturnValue({ data: { stock_inquiry: false } });
    useStockInquiryMock.mockReturnValue({ data: { revision_no: 2 }, isLoading: false });
    renderTabs();

    expect(revisionsTab()).toBeInTheDocument();
    // A disabled type DOES probe, and with the real record id.
    expect(useStockInquiryMock).toHaveBeenCalledWith('si-1');
  });

  it('hides the Revisions tab when the type is disabled and the record has never been revised', () => {
    useRevisionEnabledMapMock.mockReturnValue({ data: { stock_inquiry: false } });
    useStockInquiryMock.mockReturnValue({ data: { revision_no: 0 }, isLoading: false });
    renderTabs();

    expect(revisionsTab()).not.toBeInTheDocument();
  });

  it('hides the Revisions tab while the enabled-map query is still loading', () => {
    useRevisionEnabledMapMock.mockReturnValue({ data: undefined, isLoading: true });
    renderTabs();

    expect(revisionsTab()).not.toBeInTheDocument();
    // No answer yet, so neither probe hook has anything to key off - the
    // disabled-type probe requires `!!enabledMap`, which is undefined here.
    expect(useStockInquiryMock).toHaveBeenCalledWith(null);
  });

  it('hides the Revisions tab when the enabled-map query fails outright', () => {
    useRevisionEnabledMapMock.mockReturnValue({ data: undefined, isError: true });
    renderTabs();

    expect(revisionsTab()).not.toBeInTheDocument();
  });

  it('does not flip on for a lineage belonging to a DIFFERENT disabled type in the map', () => {
    // Only stock_inquiry is false; the entity itself still needs its own probe
    // to resolve before showing anything.
    useRevisionEnabledMapMock.mockReturnValue({
      data: { stock_inquiry: false, purchase_request: true },
    });
    useStockInquiryMock.mockReturnValue({ data: { revision_no: 0 }, isLoading: false });
    renderTabs({ revisionsKind: 'stock_inquiry' });

    expect(revisionsTab()).not.toBeInTheDocument();
  });

  it('orders tabs as Details, caller-supplied extraTabs, Revisions, then SLA Tracking', () => {
    useRevisionEnabledMapMock.mockReturnValue({ data: { stock_inquiry: true } });
    renderTabs({
      extraTabs: [{ value: 'chat', label: 'Chat records', content: <div>chat</div> }],
    });

    const tabLabels = screen.getAllByRole('tab').map((tab) => tab.textContent);
    expect(tabLabels).toEqual(['Details', 'Chat records', 'Revisions', 'SLA Tracking']);
  });

  it('orders tabs as Details, Revisions, then SLA Tracking with no extraTabs supplied', () => {
    useRevisionEnabledMapMock.mockReturnValue({ data: { stock_inquiry: true } });
    renderTabs();

    const tabLabels = screen.getAllByRole('tab').map((tab) => tab.textContent);
    expect(tabLabels).toEqual(['Details', 'Revisions', 'SLA Tracking']);
  });

  it('leaves the enabled case not probing the purchase-request hook either', () => {
    useRevisionEnabledMapMock.mockReturnValue({ data: { purchase_request: true } });
    renderTabs({ revisionsKind: 'purchase_request', sourceEntityId: 'pr-1' });

    expect(revisionsTab()).toBeInTheDocument();
    expect(usePurchaseRequestMock).toHaveBeenCalledWith(null);
    expect(useStockInquiryMock).toHaveBeenCalledWith(null);
  });

  it('probes the purchase-request hook (not stock-inquiry) for a disabled purchase_request kind', () => {
    useRevisionEnabledMapMock.mockReturnValue({ data: { purchase_request: false } });
    usePurchaseRequestMock.mockReturnValue({ data: { revision_no: 1 }, isLoading: false });
    renderTabs({ revisionsKind: 'purchase_request', sourceEntityId: 'pr-1' });

    expect(revisionsTab()).toBeInTheDocument();
    expect(usePurchaseRequestMock).toHaveBeenCalledWith('pr-1');
    expect(useStockInquiryMock).toHaveBeenCalledWith(null);
  });
});
