/**
 * PS-SAMPLE-TRACKING Stage 2 on the staff detail: the linked consignment is the delivery, so
 * Mark delivered is gone while one is linked. Mocks copied from SampleRequestDetail.test.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { SampleRequestDetail as Detail } from '@/types/sampleRequest';

const state = vi.hoisted(() => ({
  perms: new Set<string>(),
  userId: 'u-owner',
  data: undefined as unknown,
  moveAsync: vi.fn(),
  answerMutate: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
  usePathname: () => '/project-sales/sample-requests/r-1',
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => state.perms.has(slug),
}));
vi.mock('@/hooks/useEffectiveUserId', () => ({ useEffectiveUserId: () => state.userId }));
vi.mock('@/hooks/useDeferredAction', () => ({
  useDeferredAction: () => ({ countdown: null, isBlocked: false, start: vi.fn() }),
}));
vi.mock('@/lib/helpers', async (orig) => ({
  ...(await orig<typeof import('@/lib/helpers')>()),
  todayMalaysiaYyyyMmDd: () => '2026-11-02',
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/components/audit/AuditTrail', () => ({
  default: () => <div data-testid="audit-trail" />,
}));
vi.mock('@/components/common/DetailActions', () => ({
  default: ({ gear, primary }: { gear?: React.ReactNode; primary?: React.ReactNode }) => (
    <div>
      {gear}
      {primary}
    </div>
  ),
}));
vi.mock('@/components/common/DetailActionsMenu', () => ({
  DetailActionsMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenuItem: ({
    children,
    onSelect,
  }: {
    children: React.ReactNode;
    onSelect?: () => void;
  }) => <button onClick={() => onSelect?.()}>{children}</button>,
}));
vi.mock('../../_shared/components/OrderInquiryStockGrid', () => ({
  OrderInquiryStockGrid: ({ productId }: { productId: string }) => (
    <div data-testid="stock-grid">{productId}</div>
  ),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({
    resetToDefaults: () => Promise.resolve(),
    isLoading: false,
  }),
}));
vi.mock('../hooks/useSampleRequests', () => ({
  sampleRequestsPagerQuery: {},
  useSampleRequestQuery: () => ({
    data: state.data,
    isLoading: false,
    isError: false,
    error: null,
  }),
  useSampleRequestMutations: () => ({
    submit: { mutate: vi.fn(), isPending: false },
    move: { mutateAsync: state.moveAsync, isPending: false },
    saveInternal: { mutate: vi.fn(), isPending: false },
    answerDate: { mutate: state.answerMutate, isPending: false },
    linkConsignment: { mutate: vi.fn(), isPending: false },
  }),
}));
vi.mock('../services/sampleRequestService', () => ({
  downloadSampleRequestPdf: vi.fn(),
  searchSampleRequestConsignments: vi.fn().mockResolvedValue([]),
}));

import SampleRequestDetail from './SampleRequestDetail';

function Page() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <SampleRequestDetail requestId="r-1" />
    </QueryClientProvider>
  );
}

function detail(over: Partial<Detail> = {}): Detail {
  return {
    id: 'r-1',
    request_no: 'SR-000001',
    status: 'draft',
    status_label: 'Draft',
    source: 'staff',
    salesperson_id: 'u-owner',
    salesperson_name: 'Owner',
    customer_id: 'c-1',
    customer_code: 'D-001',
    customer_name: 'Acme Sdn Bhd',
    project_id: null,
    project_code: null,
    project_name: null,
    request_date: null,
    submitted_at: null,
    confirmed_at: null,
    delivered_at: null,
    return_due: null,
    cancelled_at: null,
    cancel_reason: null,
    consignment_no: null,
    po_no: null,
    created_at: '2026-10-10T01:00:00',
    updated_at: null,
    lines: [
      {
        id: 'l-1',
        line_no: 1,
        product_id: 'p-1',
        product_code: 'TILE-1',
        product_name: 'Tile One',
        brand_name: 'Brand',
        product_active: true,
        qty: 2,
        remark: null,
      },
    ],
    ...over,
  } as Detail;
}

const PROCESS = 'projects.sample_requests.process';
const CG = {
  id: 'cg-1',
  so_number: 'CG-202611-010',
  order_date: '2026-11-20',
  status: 'closed',
  delivered_on: '2026-11-22',
  delivered_source: 'tracking' as const,
};

beforeEach(() => {
  state.perms = new Set([PROCESS]);
  state.userId = 'u-coord';
  state.data = detail({
    status: 'customer_confirmed',
    status_label: 'Customer confirmed',
    delivery_date: '2026-12-01',
    date_feasible: true,
    proposed_delivery_date: null,
    date_note: null,
    consignment: null,
  });
});
afterEach(cleanup);

describe('SampleRequestDetail consignment', () => {
  it('offers Mark delivered and Link consignment with no consignment linked', () => {
    render(<Page />);
    expect(screen.getByRole('button', { name: 'Mark delivered' })).toBeInTheDocument();
    expect(screen.getByText('Link consignment')).toBeInTheDocument();
    expect(screen.getByText('Not linked')).toBeInTheDocument();
  });

  it('hides Mark delivered while a consignment is linked', () => {
    state.data = { ...(state.data as Detail), consignment: { ...CG, status: 'cancelled' } };
    render(<Page />);
    expect(screen.queryByRole('button', { name: 'Mark delivered' })).toBeNull();
    expect(screen.getByText(/^CG-202611-010 - /)).toBeInTheDocument();
    expect(screen.getByText('Voided in AutoCount')).toBeInTheDocument();
  });

  it('shows the linked consignment on a delivered request, with the date source', () => {
    state.data = {
      ...(state.data as Detail),
      status: 'delivered',
      status_label: 'Delivered',
      delivered_at: '2026-11-22',
      consignment: CG,
    };
    render(<Page />);
    expect(screen.getByText(/\(Order Tracking\)$/)).toBeInTheDocument();
    expect(screen.getByText(/^CG-202611-010 - /)).toBeInTheDocument();
    expect(screen.queryByText('Voided in AutoCount')).toBeNull();
  });

  it('does not offer Link consignment to a salesperson or before processing', () => {
    state.perms = new Set();
    render(<Page />);
    expect(screen.queryByText('Link consignment')).toBeNull();
    cleanup();
    state.perms = new Set([PROCESS]);
    state.data = { ...(state.data as Detail), status: 'submitted', status_label: 'Submitted' };
    render(<Page />);
    expect(screen.queryByText('Link consignment')).toBeNull();
  });
});
