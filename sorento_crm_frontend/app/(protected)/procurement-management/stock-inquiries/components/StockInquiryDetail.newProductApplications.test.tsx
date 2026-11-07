/**
 * StockInquiryDetail - the NEW-PRODUCT-APP entry points: the gear item that starts an
 * application from a responded inquiry, and the "New product applications" row listing what
 * was raised from it.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const push = vi.hoisted(() => vi.fn());
const applications = vi.hoisted(() => ({ data: [] as unknown[], loading: false }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  // Back, and the delete that lands where Back lands, read the list state the
  // row click wrote into this URL.
  useSearchParams: () => new URLSearchParams(''),
}));

const getFormSLATrackersMock = vi.fn();
const escalateFormTrackingMock = vi.fn();
vi.mock('@/app/(protected)/sla-management/_shared/formSLAService', () => ({
  getFormSLATrackers: (...a: unknown[]) => getFormSLATrackersMock(...a),
  escalateFormTracking: (...a: unknown[]) => escalateFormTrackingMock(...a),
}));

vi.mock('@/app/(protected)/sla-management/_shared/SlaActiveTrackerControls', () => ({
  SlaActiveTrackerControls: () => null,
}));
vi.mock('@/app/(protected)/sla-management/_shared/SlaExtendAction', () => ({
  SlaExtendMenuItem: () => null,
  SlaExtendDialog: () => null,
}));
vi.mock('@/app/(protected)/sla-management/_shared/HandlingLockBanner', () => ({
  HandlingLockBanner: () => null,
}));
vi.mock('@/app/(protected)/sla-management/_shared/HandlingLockActions', () => ({
  HandlingLockReleaseMenuItem: () => null,
}));

const handlingLockRefresh = vi.fn();
let handlingLockState: {
  state: string;
  businessCtasEnabled: boolean;
  tracker: unknown;
  claim: () => void;
  takeOver: () => void;
  release: () => void;
  refresh: () => void;
  isMutating: boolean;
} = {
  state: 'not_escalated',
  businessCtasEnabled: true,
  tracker: null,
  claim: vi.fn(),
  takeOver: vi.fn(),
  release: vi.fn(),
  refresh: handlingLockRefresh,
  isMutating: false,
};

// Form-action deferral: idle by default - these suites exercise other wiring. The
// hook's own behaviour is covered by formAction.test.ts + the pytest/e2e layers.
vi.mock('@/app/(protected)/sla-management/_shared/useFormAction', () => ({
  useFormAction: () => ({
    view: { kind: 'idle' },
    ctasDisabled: false,
    cancel: vi.fn(),
    undo: vi.fn(),
    refresh: vi.fn(),
    isMutating: false,
  }),
}));

vi.mock('@/app/(protected)/sla-management/_shared/useHandlingLock', () => ({
  useHandlingLock: () => handlingLockState,
}));

vi.mock(
  '@/app/(protected)/sla-management/conversation-sla-tracking/components/ReassignDialog',
  () => ({
    __esModule: true,
    default: ({
      open,
      onConfirm,
    }: {
      open: boolean;
      onConfirm: (userId: string) => void;
    }) =>
      open ? (
        <button type="button" onClick={() => onConfirm('user-42')}>
          Confirm reassign
        </button>
      ) : null,
  }),
);

const reassignMutateMock = vi.fn();
vi.mock(
  '@/app/(protected)/sla-management/conversation-sla-tracking/hooks/useTeamPendingSLA',
  () => ({
    useReassignSLATracking: () => ({ mutate: reassignMutateMock, isPending: false }),
  }),
);

let permissionMap: Record<string, boolean> = {};
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => permissionMap[slug] ?? false,
}));

vi.mock('@/hooks/useFormVoid', () => ({
  useFormVoid: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock('@/hooks/usePublicViewLinksEnabled', () => ({
  usePublicViewLinksEnabled: () => false,
}));

vi.mock('./StockInquiryNavigation', () => ({ __esModule: true, default: () => null }));
vi.mock('./StockInquiryAttachmentsSection', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/audit/AuditTrail', () => ({ __esModule: true, default: () => null }));

const useStockInquiryMock = vi.fn();
const updateInquiryMutateAsync = vi.fn().mockResolvedValue({});
const updateAndReplyMutateAsync = vi.fn().mockResolvedValue({});
const uploadResponseAttachmentsMutateAsync = vi.fn();
const exportPdfMutate = vi.fn();

vi.mock('@/components/common/ListPager', () => ({ __esModule: true, default: () => null }));

vi.mock('../hooks/useStockInquiries', () => ({
  // The pager reads the list page through the entity's shared key + fetch (S3-03).
  stockInquiriesPagerQuery: {
    listQueryKey: () => ['stock-inquiries'],
    fetchPage: async () => ({ data: [], pagination: { total: 0 } }),
  },
  useStockInquiry: (...a: unknown[]) => useStockInquiryMock(...a),
  useUpdateStockInquiry: () => ({ mutateAsync: updateInquiryMutateAsync, isPending: false }),
  useUpdateStockInquiryAndReply: () => ({ mutateAsync: updateAndReplyMutateAsync, isPending: false }),
  useSubmitStockInquiryForProjectSales: () => ({ mutate: vi.fn(), isPending: false }),
  useProjectSalesApproveStockInquiry: () => ({ mutate: vi.fn(), isPending: false }),
  useProjectSalesRejectStockInquiry: () => ({ mutateAsync: vi.fn(), isPending: false }),
  usePurchasingRejectStockInquiry: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useReopenStockInquiry: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUploadStockInquiryResponseAttachments: () => ({
    mutateAsync: uploadResponseAttachmentsMutateAsync,
    isPending: false,
  }),
  useDeleteStockInquiry: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useExportStockInquiryPdf: () => ({ mutate: exportPdfMutate, isPending: false }),
  useStockInquiryRevisions: () => ({ data: [], isLoading: false, isError: false }),
}));

vi.mock('../../new-product-applications/hooks/useNewProductApplications', () => ({
  useStockInquiryApplicationsQuery: (_id: string | null, enabled: boolean) => ({
    data: enabled && !applications.loading ? applications.data : undefined,
    isLoading: enabled && applications.loading,
  }),
}));

import StockInquiryDetail from './StockInquiryDetail';

function inquiry(over: Record<string, unknown> = {}) {
  return {
    id: 'si-1',
    inquiry_number: 'SI26-0412',
    status: 'responded',
    created_at: '2026-07-01T00:00:00Z',
    purchasing_response: '',
    respond_inbox_url: null,
    attachments: [],
    ...over,
  };
}

function renderPage() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <StockInquiryDetail inquiryId="si-1" />
    </QueryClientProvider>,
  );
}

function renderPageWithUnmount() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <StockInquiryDetail inquiryId="si-1" />
    </QueryClientProvider>,
  );
}

async function openGearMenu() {
  const trigger = await screen.findByRole('button', { name: 'Stock inquiry actions' });
  fireEvent.pointerDown(trigger, { button: 0, pointerId: 1 });
  fireEvent.pointerUp(trigger, { button: 0, pointerId: 1 });
  fireEvent.click(trigger);
  await waitFor(() => expect(trigger.getAttribute('aria-expanded')).toBe('true'));
}

const CREATE = 'procurement.new_product_applications.create';
const VIEW = 'procurement.new_product_applications.view';

beforeEach(() => {
  vi.clearAllMocks();
  permissionMap = {};
  applications.data = [];
  applications.loading = false;
  handlingLockState = {
    state: 'not_escalated',
    businessCtasEnabled: true,
    tracker: null,
    claim: vi.fn(),
    takeOver: vi.fn(),
    release: vi.fn(),
    refresh: handlingLockRefresh,
    isMutating: false,
  };
  useStockInquiryMock.mockReturnValue({ data: inquiry(), isLoading: false });
  getFormSLATrackersMock.mockResolvedValue([]);
});

describe('StockInquiryDetail - Create new product application gear item', () => {
  it('shows on a responded inquiry for a create holder and opens the New form on that inquiry', async () => {
    permissionMap = { [CREATE]: true };
    renderPage();
    await openGearMenu();
    fireEvent.click(await screen.findByText('Create new product application'));
    expect(push).toHaveBeenCalledWith(
      '/procurement-management/new-product-applications/new?stock_inquiry_id=si-1',
    );
  });

  it('is absent without the create permission', async () => {
    permissionMap = { [VIEW]: true };
    renderPage();
    await openGearMenu();
    await screen.findByText('Download history');
    expect(screen.queryByText('Create new product application')).toBeNull();
  });

  it('is absent on an inquiry that is not responded', async () => {
    permissionMap = { [CREATE]: true };
    useStockInquiryMock.mockReturnValue({
      data: inquiry({ status: 'pending_purchasing' }),
      isLoading: false,
    });
    renderPage();
    await openGearMenu();
    await screen.findByText('Download history');
    expect(screen.queryByText('Create new product application')).toBeNull();
  });
});

const openTab = (name: RegExp) =>
  fireEvent.mouseDown(screen.getByRole('tab', { name }));

describe('StockInquiryDetail - New product applications tab', () => {
  it('shows the empty state when nothing was raised from the inquiry', async () => {
    permissionMap = { [VIEW]: true };
    renderPage();
    await screen.findByText('Stock inquiry number');
    openTab(/new product applications \(0\)/i);
    expect(await screen.findByText('No new product applications')).toBeInTheDocument();
    expect(
      screen.getByText('Applications created from this inquiry show here.'),
    ).toBeInTheDocument();
    // the form is the other tab
    expect(screen.queryByText('Stock inquiry number')).toBeNull();
  });

  it('lists number (link), status, current codes -> new code and date', async () => {
    permissionMap = { [VIEW]: true };
    applications.data = [
      {
        id: 'a-1',
        application_no: 'NPA-000001',
        status: 'completed',
        status_label: 'Completed',
        created_at: '2026-11-03T02:00:00',
        opened_codes: ['XY-1234-MB-69'],
        created_codes: [
          { product_code: 'XY-1234-MB-69', current_codes: ['XY-1234-MB'], created_at: '2026-11-03T02:00:00' },
        ],
      },
    ];
    renderPage();
    openTab(/new product applications \(1\)/i);
    const link = await screen.findByRole('link', { name: 'NPA-000001' });
    expect(link).toHaveAttribute('href', '/procurement-management/new-product-applications/a-1');
    expect(screen.getAllByText('Completed').length).toBeGreaterThan(0);
    expect(screen.getByText('XY-1234-MB -> XY-1234-MB-69')).toBeInTheDocument();
    expect(screen.getByText('03/11/2026')).toBeInTheDocument();
  });

  it('is hidden for a user with no new product application permission', async () => {
    renderPage();
    await screen.findByText('Stock inquiry number');
    expect(screen.queryByRole('tab', { name: /new product applications/i })).toBeNull();
  });
});

describe('StockInquiryDetail - next-step banners', () => {
  const ASK = 'Purchasing asks the salesperson to create a New Product Application.';

  it('asks while purchasing asked and no live application exists', async () => {
    permissionMap = { [VIEW]: true };
    useStockInquiryMock.mockReturnValue({
      data: inquiry({ npa_requested: true }),
      isLoading: false,
    });
    applications.data = [
      { id: 'a-0', application_no: 'NPA-000000', status: 'cancelled', status_label: 'Cancelled', created_codes: [] },
    ];
    renderPage();
    expect(await screen.findByText(ASK)).toBeInTheDocument();
  });

  it('does not ask once a live application exists, nor when nobody asked', async () => {
    permissionMap = { [VIEW]: true };
    useStockInquiryMock.mockReturnValue({
      data: inquiry({ npa_requested: true }),
      isLoading: false,
    });
    applications.data = [
      { id: 'a-1', application_no: 'NPA-000001', status: 'submitted', status_label: 'Submitted', created_codes: [] },
    ];
    const { unmount } = renderPageWithUnmount();
    await screen.findByText('Stock inquiry number');
    expect(screen.queryByText(ASK)).toBeNull();
    unmount();

    useStockInquiryMock.mockReturnValue({ data: inquiry({ npa_requested: false }), isLoading: false });
    applications.data = [];
    renderPage();
    await screen.findByText('Stock inquiry number');
    expect(screen.queryByText(ASK)).toBeNull();
  });

  it('turns green with the new code, date and application number', async () => {
    permissionMap = { [VIEW]: true };
    useStockInquiryMock.mockReturnValue({
      data: inquiry({ npa_requested: true }),
      isLoading: false,
    });
    applications.data = [
      {
        id: 'a-1',
        application_no: 'NPA-000001',
        status: 'completed',
        status_label: 'Completed',
        created_codes: [
          { product_code: 'XY-1234-MB-69', current_codes: ['XY-1234-MB'], created_at: '2026-11-03T02:00:00' },
        ],
      },
    ];
    renderPage();
    expect(
      await screen.findByText('New code XY-1234-MB-69 created on 03/11/2026 (NPA-000001).'),
    ).toBeInTheDocument();
    expect(screen.queryByText(ASK)).toBeNull();
  });
});

describe('StockInquiryDetail - banners only with NPA access and loaded data (NPA-FROM-SI)', () => {
  const ASK = 'Purchasing asks the salesperson to create a New Product Application.';
  const CREATED = /New code XY-1234-MB-69 created on 03\/11\/2026 \(NPA-000001\)\./;
  const done = [
    {
      id: 'a-1',
      application_no: 'NPA-000001',
      status: 'completed',
      status_label: 'Completed',
      created_codes: [
        { product_code: 'XY-1234-MB-69', current_codes: ['XY-1234-MB'], created_at: '2026-11-03T02:00:00' },
      ],
    },
  ];

  it('shows neither banner to a user with no application permission, even when asked', async () => {
    useStockInquiryMock.mockReturnValue({ data: inquiry({ npa_requested: true }), isLoading: false });
    applications.data = done;
    renderPage();
    await screen.findByText('Stock inquiry number');
    expect(screen.queryByText(ASK)).toBeNull();
    expect(screen.queryByText(CREATED)).toBeNull();
  });

  it('shows no ask while the applications are still loading', async () => {
    permissionMap = { [VIEW]: true };
    useStockInquiryMock.mockReturnValue({ data: inquiry({ npa_requested: true }), isLoading: false });
    applications.loading = true;
    renderPage();
    await screen.findByText('Stock inquiry number');
    expect(screen.queryByText(ASK)).toBeNull();
    expect(screen.queryByText(CREATED)).toBeNull();
  });

  it('shows the ask once the applications have loaded empty', async () => {
    permissionMap = { [VIEW]: true };
    useStockInquiryMock.mockReturnValue({ data: inquiry({ npa_requested: true }), isLoading: false });
    applications.data = [];
    renderPage();
    expect(await screen.findByText(ASK)).toBeInTheDocument();
  });
});

describe('StockInquiryDetail - Salesperson must create a New Product Application', () => {
  const BOX = 'Salesperson must create a New Product Application';

  async function openDialog() {
    const edit = await waitFor(() => {
      const el = document.querySelector(
        '[data-guide-target="procurement.stock-inquiries.edit-purchasing-response-button"]',
      );
      expect(el).not.toBeNull();
      return el as HTMLElement;
    });
    fireEvent.click(edit);
    return screen.findByRole('checkbox', { name: BOX });
  }

  it('starts from the saved flag and Save only sends it', async () => {
    useStockInquiryMock.mockReturnValue({
      data: inquiry({ npa_requested: true, purchasing_response: 'ok' }),
      isLoading: false,
    });
    renderPage();
    const box = await openDialog();
    expect(box).toHaveAttribute('aria-checked', 'true');
    fireEvent.click(box);
    fireEvent.click(screen.getByRole('button', { name: 'Save only' }));
    await waitFor(() =>
      expect(updateInquiryMutateAsync).toHaveBeenCalledWith({
        id: 'si-1',
        data: { purchasing_response: 'ok', npa_requested: false },
      }),
    );
  });

  it('Update & Reply carries the ticked box on both writes', async () => {
    useStockInquiryMock.mockReturnValue({
      data: inquiry({
        npa_requested: false,
        purchasing_response: 'ok',
        respond_inbox_url: 'https://inbox.example/1',
      }),
      isLoading: false,
    });
    renderPage();
    const box = await openDialog();
    expect(box).toHaveAttribute('aria-checked', 'false');
    fireEvent.click(box);
    fireEvent.click(screen.getByRole('button', { name: /update & reply/i }));
    await waitFor(() => expect(updateAndReplyMutateAsync).toHaveBeenCalled());
    const want = { purchasing_response: 'ok', npa_requested: true };
    expect(updateInquiryMutateAsync).toHaveBeenCalledWith({ id: 'si-1', data: want });
    expect(updateAndReplyMutateAsync).toHaveBeenCalledWith({ id: 'si-1', data: want });
  });
});
