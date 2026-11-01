/**
 * NAV-KEEP-TAB, page level: the complaint detail (Details, Comments, Fulfilment DOs, Revisions,
 * SLA Tracking) opens the tab named by `?tab=`, which is what the record pager carries to the
 * next complaint. Owner's case: on "Fulfilment DOs", next lands on the next complaint's
 * Fulfilment DOs. A tab the next record lacks (Revisions hidden) falls back to Details.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { watchTabWrites } from '@/test-mocks/urlTab';

let search = '';
vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(search),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/complaint-management/complaints/cp-1',
}));

const mapMock = vi.fn();
vi.mock('./useRevisionEnabledMap', () => ({ useRevisionEnabledMap: () => mapMock() }));
vi.mock('./FormSLATrackingTab', () => ({ __esModule: true, default: () => <div>sla body</div> }));
vi.mock('@/components/common/comments/FormComments', () => ({ FormComments: () => <div>thread</div> }));
vi.mock('@/hooks/useFormComments', () => ({ useFormCommentsQuery: () => ({ data: [] }) }));
vi.mock('@/hooks/useRequestScope', () => ({ useRequestScope: () => ({ limited: false }) }));
vi.mock('@/app/(protected)/complaint-management/complaints/hooks/useComplaints', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useComplaint: () => ({ data: undefined }),
}));
vi.mock('@/app/(protected)/procurement-management/stock-inquiries/hooks/useStockInquiries', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  useStockInquiry: () => ({ data: undefined }),
}));
vi.mock('@/app/(protected)/procurement-management/purchase-requests/hooks/usePurchaseRequests', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  usePurchaseRequest: () => ({ data: undefined }),
}));
vi.mock('./FormRevisionsTab', () => ({ __esModule: true, default: () => <div>revisions body</div> }));

import FormDetailTabsWithRevisions from './FormDetailTabsWithRevisions';
import { RecordCardSlot } from './RecordCardSlot';

/** The complaint detail page's own composition (`complaints/[id]/page.tsx`). */
function mountComplaint(id: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <FormDetailTabsWithRevisions
        sourceEntityType="complaint"
        sourceEntityId={id}
        revisionsKind="complaint"
        commentsKind="complaint"
        extraTabs={[{ value: 'fulfilment', label: 'Fulfilment DOs', content: <div>dos of {id}</div> }]}
      >
        {/* What ComplaintDetail renders: the record card (pager inside) through the slot,
            then the Details body. */}
        <RecordCardSlot>
          <button type="button">Next complaint</button>
        </RecordCardSlot>
        <div>details of {id}</div>
      </FormDetailTabsWithRevisions>
    </QueryClientProvider>,
  );
}
const selected = () => screen.getAllByRole('tab').find((t) => t.getAttribute('aria-selected') === 'true')?.textContent;

beforeEach(() => {
  cleanup();
  search = '';
  mapMock.mockReturnValue({ data: { complaint: true } });
});

describe('Complaint detail keeps the tab across prev/next', () => {
  it('opens on Details with no ?tab=', () => {
    mountComplaint('cp-1');
    expect(selected()).toBe('Details');
  });

  it('the next complaint opened with ?tab=fulfilment (what the pager pushes) is on Fulfilment DOs', () => {
    search = 'page=1&limit=50&sort=created_at&dir=desc&from=cp-2&tab=fulfilment';
    mountComplaint('cp-2');
    expect(selected()).toBe('Fulfilment DOs');
    expect(screen.getByText('dos of cp-2')).toBeTruthy();
  });

  it('picking a tab writes ?tab= and keeps the list state on the URL', () => {
    search = 'page=2&limit=50&status=open';
    const written = watchTabWrites('/complaint-management/complaints/cp-1', search);
    mountComplaint('cp-1');
    fireEvent.mouseDown(screen.getByRole('tab', { name: /Fulfilment DOs/ }), { button: 0, ctrlKey: false });
    expect(selected()).toBe('Fulfilment DOs');
    const url = new URL(written()!, 'http://h');
    expect(url.pathname).toBe('/complaint-management/complaints/cp-1');
    expect(url.searchParams.get('tab')).toBe('fulfilment');
    expect(url.searchParams.get('page')).toBe('2');
    expect(url.searchParams.get('status')).toBe('open');
  });

  it('falls back to Details when the next complaint has no such tab (Revisions hidden)', () => {
    mapMock.mockReturnValue({ data: { complaint: false } });
    search = 'tab=revisions';
    mountComplaint('cp-3');
    expect(selected()).toBe('Details');
    expect(screen.getByText('details of cp-3')).toBeTruthy();
  });
});

describe('The record card (and its pager) is on every tab', () => {
  it('on Fulfilment DOs the pager is still there, above the tab strip', () => {
    search = 'tab=fulfilment';
    mountComplaint('cp-2');
    const next = screen.getByRole('button', { name: 'Next complaint' });
    expect(next).toBeTruthy();
    // Above the strip, not inside a tab panel.
    expect(next.closest('[role="tabpanel"]')).toBeNull();
    const strip = screen.getByRole('tablist');
    expect(next.compareDocumentPosition(strip) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('on SLA Tracking too, and the Details body is hidden there', () => {
    search = 'tab=sla';
    mountComplaint('cp-2');
    expect(screen.getByRole('button', { name: 'Next complaint' })).toBeTruthy();
    expect(screen.getByText('details of cp-2').closest('[role="tabpanel"]')?.getAttribute('data-state')).toBe(
      'inactive',
    );
  });
});
