/**
 * PORTAL-P4-REQUESTS review fix (red): a LIMITED user (view_own without view) must not get the
 * SLA Tracking tab (it reads /conversation-sla-tracking/by-source, which needs .view), and on the
 * complaint page not the Fulfilment DOs tab either. Staff keep both.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('./useRevisionEnabledMap', () => ({ useRevisionEnabledMap: () => ({ data: {} }) }));
vi.mock('./FormSLATrackingTab', () => ({ __esModule: true, default: () => <div data-testid="sla" /> }));
vi.mock('@/components/common/comments/FormComments', () => ({ FormComments: () => <div>thread</div> }));
vi.mock('@/hooks/useFormComments', () => ({ useFormCommentsQuery: () => ({ data: [] }) }));
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
// The complaint page's own pieces.
vi.mock('@/app/(protected)/complaint-management/complaints/components/ComplaintDetail', () => ({ __esModule: true, default: () => <div>complaint detail</div> }));
vi.mock('@/app/(protected)/complaint-management/complaints/components/ComplaintFulfilmentOrdersSection', () => ({ __esModule: true, default: () => <div>dos</div> }));
vi.mock('@/components/common/RecordEntityRegistrar', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/common/BackToList', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/common/PageHeader', () => ({ PageHeader: () => null }));
vi.mock('@/components/common/container', () => ({ Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));

let held = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => held.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => held.has(s)),
  usePermissions: () => ({ permissionSet: held, permissions: [...held], isLoading: false, isError: false }),
}));

import FormDetailTabsWithRevisions from './FormDetailTabsWithRevisions';
import SampleRequestDetailTabs from '@/app/(protected)/project-sales/sample-requests/components/SampleRequestDetailTabs';
import ComplaintDetailPage from '@/app/(protected)/complaint-management/complaints/[id]/page';

const KINDS: Array<[string, string, string]> = [
  ['stock_inquiry', 'stock_inquiry', 'procurement.stock_inquiries'],
  ['complaint', 'complaint', 'complaint_management.complaints'],
  ['purchase_request', 'purchase_request', 'procurement.purchase_requests'],
  ['sponsorship_form', 'purchase_request', 'procurement.sponsorship_forms'],
];

const wrap = (ui: React.ReactElement) =>
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>);
const tabs = () => screen.getAllByRole('tab').map((t) => t.textContent);

beforeEach(() => {
  cleanup();
  held = new Set();
});

describe.each(KINDS)('%s detail tabs', (source, revisionsKind, base) => {
  const mount = () =>
    wrap(
      <FormDetailTabsWithRevisions sourceEntityType={source as never} sourceEntityId="r-1" revisionsKind={revisionsKind as never}>
        <div>Details content</div>
      </FormDetailTabsWithRevisions>,
    );

  it('staff (view): SLA Tracking tab stays', () => {
    held = new Set([`${base}.view`, `${base}.view_own`]);
    mount();
    expect(tabs()).toContain('SLA Tracking');
  });
});

describe('complaint page', () => {
  async function mountPage() {
    // The page renders a server-side async wrapper; resolve it to its element, then mount that.
    const root = ComplaintDetailPage({ params: Promise.resolve({ id: 'cp-1' }) }) as React.ReactElement;
    const find = (node: unknown): React.ReactElement | null => {
      if (!React.isValidElement(node)) return null;
      const el = node as React.ReactElement<{ children?: React.ReactNode }>;
      if (typeof el.type === 'function' && el.type.constructor.name === 'AsyncFunction') return el;
      const kids = React.Children.toArray(el.props.children);
      for (const k of kids) {
        const hit = find(k);
        if (hit) return hit;
      }
      return null;
    };
    const asyncEl = find(root);
    const inner = asyncEl
      ? await (asyncEl.type as (p: unknown) => Promise<React.ReactElement>)(asyncEl.props)
      : root;
    wrap(inner);
  }

  it('limited user: no Fulfilment DOs tab, and no outer tab strip (R1: the portal form carries its own)', async () => {
    held = new Set(['complaint_management.complaints.view_own']);
    await mountPage();
    await new Promise((r) => setTimeout(r, 50));
    const names = screen.queryAllByRole('tab').map((t) => t.textContent);
    expect(names).not.toContain('Fulfilment DOs');
    expect(names).not.toContain('Details');
  });

  it('staff: Fulfilment DOs tab stays', async () => {
    held = new Set(['complaint_management.complaints.view', 'complaint_management.complaints.view_own']);
    await mountPage();
    await waitFor(() => expect(tabs()).toContain('Fulfilment DOs'));
  });
});

describe('sample request detail tabs', () => {
  const mount = () =>
    wrap(
      <SampleRequestDetailTabs id="sr-1">
        <div>Details content</div>
      </SampleRequestDetailTabs>,
    );

  it('limited user (view_own, no view): children only, no tab strip (the portal form carries its own)', () => {
    held = new Set(['projects.sample_requests.view_own']);
    mount();
    expect(screen.getByText('Details content')).toBeInTheDocument();
    expect(screen.queryAllByRole('tab')).toHaveLength(0);
  });

  it('staff (view): SLA Tracking tab stays', () => {
    held = new Set(['projects.sample_requests.view', 'projects.sample_requests.view_own']);
    mount();
    expect(tabs()).toContain('SLA Tracking');
  });
});
