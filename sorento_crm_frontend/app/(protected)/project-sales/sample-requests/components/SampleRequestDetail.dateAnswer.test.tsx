/**
 * PS-SAMPLE-TRACKING Stage 1 on the staff detail: Start processing asks the date answer, the
 * salesperson reads it, the team changes it. Mocks copied from SampleRequestDetail.test.tsx.
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
  }),
}));
vi.mock('../services/sampleRequestService', () => ({ downloadSampleRequestPdf: vi.fn() }));

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

beforeEach(() => {
  state.perms = new Set([PROCESS]);
  state.userId = 'u-coord';
  state.moveAsync = vi.fn().mockResolvedValue({});
  state.answerMutate = vi.fn();
  state.data = detail({
    status: 'submitted',
    status_label: 'Submitted',
    delivery_date: '2026-12-01',
    date_feasible: null,
    proposed_delivery_date: null,
    date_note: null,
  });
});
afterEach(cleanup);

describe('SampleRequestDetail date answer', () => {
  it('Start processing with Yes sends date_feasible true', async () => {
    render(<Page />);
    fireEvent.click(screen.getByRole('button', { name: 'Change to processing' }));
    const confirm = screen.getAllByRole('button', { name: 'Change to processing' }).at(-1)!;
    expect(confirm).toBeDisabled();
    fireEvent.click(screen.getByLabelText('Yes, we can meet it'));
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    expect(state.moveAsync).toHaveBeenCalledWith({
      id: 'r-1',
      body: { to: 'processing', date_feasible: true },
    });
  });

  it('No needs a proposed date, today or later, and sends it with the note', () => {
    render(<Page />);
    fireEvent.click(screen.getByRole('button', { name: 'Change to processing' }));
    const confirm = screen.getAllByRole('button', { name: 'Change to processing' }).at(-1)!;
    fireEvent.click(screen.getByLabelText('No, propose a new date'));
    expect(confirm).toBeDisabled();
    const date = screen.getByLabelText('Proposed date *');
    fireEvent.change(date, { target: { value: '2026-11-01' } });
    expect(screen.getByText('The proposed date cannot be in the past.')).toBeInTheDocument();
    expect(confirm).toBeDisabled();
    fireEvent.change(date, { target: { value: '2026-12-09' } });
    fireEvent.change(screen.getByLabelText('Note'), { target: { value: 'Stock from KL' } });
    fireEvent.click(confirm);
    expect(state.moveAsync).toHaveBeenCalledWith({
      id: 'r-1',
      body: {
        to: 'processing',
        date_feasible: false,
        proposed_delivery_date: '2026-12-09',
        date_note: 'Stock from KL',
      },
    });
  });

  it('shows the salesperson the proposed date with a New date badge and the note', () => {
    state.perms = new Set();
    state.userId = 'u-owner';
    state.data = detail({
      status: 'processing',
      status_label: 'Processing',
      delivery_date: '2026-12-01',
      date_feasible: false,
      proposed_delivery_date: '2026-12-09',
      date_note: 'Stock from KL',
    });
    render(<Page />);
    expect(screen.getByText(/^Proposes /)).toBeInTheDocument();
    expect(screen.getByText('New date')).toBeInTheDocument();
    expect(screen.getByText('Stock from KL')).toBeInTheDocument();
    expect(screen.queryByText('Change date answer')).toBeNull();
  });

  it('reads Not answered yet before Start processing', () => {
    render(<Page />);
    expect(screen.getByText('Not answered yet')).toBeInTheDocument();
    expect(screen.queryByText('Change date answer')).toBeNull();
  });

  it('lets the team change the answer while processing', () => {
    state.data = detail({
      status: 'processing',
      status_label: 'Processing',
      delivery_date: '2026-12-01',
      date_feasible: true,
      proposed_delivery_date: null,
      date_note: null,
    });
    render(<Page />);
    expect(screen.getByText('Can meet the requested date')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Change date answer'));
    fireEvent.click(screen.getByLabelText('No, propose a new date'));
    fireEvent.change(screen.getByLabelText('Proposed date *'), {
      target: { value: '2026-12-20' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(state.answerMutate).toHaveBeenCalledWith(
      { id: 'r-1', body: { date_feasible: false, proposed_delivery_date: '2026-12-20' } },
      expect.anything(),
    );
  });
});
