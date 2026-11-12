/**
 * DATE-PICKER-UNIFY slice B: the LoadingPlanView "Change cut-off" dialog ("Sales orders
 * needed") is ONE typeable range field, pre-filled dd/mm/yyyy, saving the same two params.
 * Harness copied from LoadingPlanView.test.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { watchTabWrites } from '@/test-mocks/urlTab';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { LoadingPlanRecord } from '../../services/fulfilmentService';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
  });
}
if (!window.ResizeObserver) {
  (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

const push = vi.fn();
const replace = vi.fn();
// The URL is what the tab strip reads and writes (AC-B2) - a real `URLSearchParams` so
// `.get('tab')` and `.toString()` both behave, swappable per test to prove a reload lands
// back on the tab named in it.
let currentSearchParams = new URLSearchParams();
// The pager has its own tests (hooks/useListPager.test.ts).
vi.mock('@/components/common/ListPager', () => ({ __esModule: true, default: () => null }));

vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/loading-plan/plan-1',
  useRouter: () => ({ push, replace }),
  useSearchParams: () => currentSearchParams,
}));

vi.mock('@/lib/toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
    custom: vi.fn(),
  },
}));

// The gear menu, flattened: Radix opens on pointerdown through a portal, and what this suite
// asks of it is which items it offers, not how it animates.
/* eslint-disable @typescript-eslint/no-explicit-any */
vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: any) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: any) => <>{children}</>,
  DropdownMenuContent: ({ children }: any) => <div data-testid="menu-content">{children}</div>,
  DropdownMenuItem: ({ children, onSelect, disabled, ...rest }: any) => (
    <button type="button" onClick={onSelect} disabled={disabled} {...rest}>
      {children}
    </button>
  ),
  DropdownMenuLabel: ({ children }: any) => <div>{children}</div>,
  DropdownMenuSeparator: () => <hr />,
  DropdownMenuGroup: ({ children }: any) => <div>{children}</div>,
  DropdownMenuPortal: ({ children }: any) => <>{children}</>,
}));
/* eslint-enable @typescript-eslint/no-explicit-any */

// The tab has its own suite (SupplierCodesTab.test.tsx); here it only has to prove it
// mounted, on the codes tab and nowhere else.
vi.mock('./SupplierCodesTab', () => ({
  SupplierCodesTab: () => <div data-testid="supplier-codes-tab" />,
}));

// The grid is a controlled child now (R5): the record owns the typed quantities, so the stub
// exposes exactly the two props that carry them.
vi.mock('./ContainerRequestSection', () => ({
  ContainerRequestSection: ({
    supplierName,
    readOnly,
    onQtyChange,
    remarkFor,
  }: {
    supplierName: string;
    readOnly?: boolean;
    onQtyChange: (rowKey: string, qty: number) => void;
    remarkFor: (row: { row_key: string }) => string;
  }) => (
    <div data-testid="container-request-section" data-readonly={String(!!readOnly)}>
      Request section for {supplierName}
      <button type="button" data-testid="type-qty" onClick={() => onQtyChange('row-a', 4000)}>
        type
      </button>
      <button
        type="button"
        data-testid="type-engine-qty"
        onClick={() => onQtyChange('row-a', 4242)}
      >
        type the engine figure
      </button>
      {/* S2, review round 1: the SAME `remarkFor` the preview's own input writes through -
          reading it here off the row this suite's fixture always keys `row-a` is what proves
          a remark typed in the preview shows in the plan table without a save. */}
      <span data-testid="plan-table-remark">{remarkFor({ row_key: 'row-a' } as never)}</span>
    </div>
  ),
}));

const ENGINE_ROW = {
  row_key: 'row-a',
  product_id: 'prod-a',
  row_kind: 'product' as const,
  product_set_id: null,
  suggested_qty: 4242,
  engine_qty: 4242,
  cbm_per_unit: 0.5,
};

const PLAN: LoadingPlanRecord = {
  id: 'plan-1',
  supplier_id: 'sup-1',
  supplier_name: 'CHAOZHOU JINBAICHUAN SANITARY WARE CO., LTD',
  supplier_email: 'person36@example.com',
  started_at: '2026-08-27T14:02:00',
  plan_horizon_start: null,
  plan_horizon_date: '2026-09-30',
  document_kind: 'stock_list',
  document_label: 'Stock list 27/07/2026',
  statement_as_of: '2026-07-27',
  source_attachment_id: 'att-1',
  source_attachment_filename: 'plan-own-list.xlsx',
  status: 'planning',
  sent_channel: null,
  sent_at: null,
  opened_at: null,
  last_opened_at: null,
  open_count: 0,
  cancelled_at: null,
  cancelled_by: null,
  line_edits: {},
  to_request_qty: null,
  to_request_cbm: null,
};

const state = {
  plan: PLAN,
  rows: [ENGINE_ROW],
  /** Make the pre-send Save refuse, which used to leave an unhandled rejection and send anyway. */
  saveFails: false,
  /** The Supplier codes tab's badge count (S2) - empty by default in this suite, which is
   *  about the toolbar and the Lines tab, not the queue itself (`SupplierCodesTab` and
   *  `SentRequestsPanel` own their own contents; `LoadingPlanView.test.tsx` (tabs) covers
   *  the strip and the badges). */
  unmatchedCodes: [] as unknown[],
  /** The Sent tab's badge count and body (S2). */
  notices: [] as unknown[],
  /** Which supplier the legacy stock-list lookup was asked about, or null when the record
   *  read the plan's own stamped file instead (BL-3). */
  stockListFileAskedAbout: null as string | null,
  /** R9 preview page state: the sheet `useContainerRequestPreview` answers with, null when a
   *  test does not open the preview. */
  previewSheet: null as unknown,
};

const saveEdits = vi.fn();
const sendRequest = vi.fn();
const changeCutOff = vi.fn();
const refetchBuild = vi.fn();

vi.mock('../../hooks/useFulfilment', () => ({
  // The pager reads the list page through the entity's shared key + fetch (S3-03).
  loadingPlanPagerQuery: {
    listQueryKey: () => ['scm-loading-plans'],
    fetchPage: async () => ({ data: [], pagination: { total: 0 } }),
  },
  useContainerRequestBuild: () => ({
    data: { plan: state.plan, rows: state.rows, supplier_id: 'sup-1' },
    isLoading: false,
    isError: false,
    isFetching: false,
    error: null,
    refetch: refetchBuild,
  }),
  // R9: `state.previewSheet` stays null (the steady "nothing yet" answer) except in the one
  // test that opens the preview and sets it - both keep the hook count and the component
  // happy without every other test's build needing a sheet fixture of its own.
  useContainerRequestPreview: () => ({ data: state.previewSheet, isError: false, error: null }),
  useSaveLoadingPlanEdits: () => ({
    mutate: (v: unknown, o?: { onSuccess?: () => void }) => {
      saveEdits(v);
      o?.onSuccess?.();
    },
    mutateAsync: async (v: unknown) => {
      saveEdits(v);
      if (state.saveFails) throw new Error('The quantities could not be saved.');
      return state.plan;
    },
    isPending: false,
  }),
  useUpdateLoadingPlanCutOff: () => ({ mutate: changeCutOff, isPending: false }),
  useSendContainerRequest: () => ({
    mutate: (v: unknown, o?: { onSuccess?: () => void }) => {
      sendRequest(v);
      o?.onSuccess?.();
    },
    isPending: false,
    error: null,
    reset: vi.fn(),
  }),
  useSupplierChatContacts: () => ({
    data: {
      data: [],
      total: 0,
      wechat_connected: false,
      wechat_channel_name: null,
      unavailable_reason: 'No WeChat channel is connected in the Respond.io workspace.',
    },
    isLoading: false,
  }),
  useDownloadContainerRequestDocument: () => ({ mutate: vi.fn(), isPending: false }),
  useLoadingPlanList: () => ({ data: { data: [{ id: 'plan-1' }], total: 1 } }),
  useSupplierNotices: () => ({ data: state.notices }),
  useSupplierStockListFile: (supplierId: string | null) => {
    state.stockListFileAskedAbout = supplierId;
    return {
      data: supplierId ? { attachment_id: 'att-supplier', filename: 'supplier.xlsx' } : null,
      isLoading: false,
    };
  },
}));

vi.mock('../../hooks/useSupplierCodeAliases', () => ({
  useRematchSupplierCodes: () => ({ mutate: vi.fn(), isPending: false }),
  useUnmatchedSupplierCodes: () => ({ data: state.unmatchedCodes }),
}));

import { LoadingPlanView } from './LoadingPlanView';

function renderView() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <LoadingPlanView planId="plan-1" />
    </QueryClientProvider>,
  );
}

describe('LoadingPlanView (the record)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    state.plan = { ...PLAN };
    state.rows = [ENGINE_ROW];
    state.saveFails = false;
    state.unmatchedCodes = [];
    state.notices = [];
    state.stockListFileAskedAbout = null;
    state.previewSheet = null;
    currentSearchParams = new URLSearchParams();
  });


  const RANGE_PH = 'DD/MM/YYYY - DD/MM/YYYY';

  it('AC1/AC3: the dialog shows the stored window as dd/mm/yyyy in ONE range field, no native input', async () => {
    state.plan = {
      ...PLAN,
      plan_horizon_date: '2026-10-31',
      plan_horizon_start: '2026-10-01',
    } as LoadingPlanRecord;
    renderView();
    fireEvent.click(screen.getByRole('button', { name: 'Change cut-off' }));
    await screen.findByText('Sales orders needed');

    expect(document.body.querySelector('input[type="date"]')).toBeNull();
    expect(screen.getAllByPlaceholderText(RANGE_PH)).toHaveLength(1);
    expect(screen.getByPlaceholderText(RANGE_PH)).toHaveValue('01/10/2026 - 31/10/2026');
  });

  it('AC2/AC9: typing a range and pressing Enter saves the same plan_horizon_start / plan_horizon_date', async () => {
    renderView();
    fireEvent.click(screen.getByRole('button', { name: 'Change cut-off' }));
    const range = await screen.findByPlaceholderText(RANGE_PH);
    fireEvent.change(range, { target: { value: '01/09/2026 - 31/10/2026' } });
    fireEvent.keyDown(range, { key: 'Enter' });
    fireEvent.click(screen.getAllByRole('button', { name: 'Save cut-off' })[0]);

    await waitFor(() =>
      expect(changeCutOff).toHaveBeenCalledWith(
        expect.objectContaining({
          plan_horizon_start: '2026-09-01',
          plan_horizon_date: '2026-10-31',
        }),
        expect.anything(),
      ),
    );
  });
});
