/**
 * The loading plan RECORD (part 4, R5 / R6 - AC-A12, A13, A14, A15, A16, the read-only half
 * of A8, and S1's AC-A2).
 *
 * What this suite pins is the toolbar: the supplier is the title, the subtitle states
 * started / cut-off / document, the status is a badge, and the right cluster reads
 * [pager] [gear] [Save (N)] [Back] - Send to supplier moved into the gear (captain's markup,
 * 2 Sep), so there is no standalone Send button any more. Save counts the rows that differ
 * from the engine's own answer, Send saves before it sends, leaving with unsaved edits asks,
 * and a cancelled plan can do neither.
 *
 * The ranked grid inside it is `ContainerRequestSection.test.tsx`; the popup that starts a
 * plan is `PlanContainerDialog.test.tsx`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
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

vi.mock('sonner', () => ({
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
  }: {
    supplierName: string;
    readOnly?: boolean;
    onQtyChange: (rowKey: string, qty: number) => void;
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
  supplier_email: 'sales@jinbaichuan.cn',
  started_at: '2026-08-27T14:02:00',
  plan_horizon_date: '2026-09-30',
  document_kind: 'stock_list',
  document_label: 'Stock list 27/07/2026',
  source_attachment_id: 'att-1',
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
};

const saveEdits = vi.fn();
const sendRequest = vi.fn();
const cancelPlan = vi.fn();
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
  useCancelLoadingPlan: () => ({ mutate: cancelPlan, isPending: false }),
  useDownloadContainerRequestDocument: () => ({ mutate: vi.fn(), isPending: false }),
  useLoadingPlanList: () => ({ data: { data: [{ id: 'plan-1' }], total: 1 } }),
  useSupplierNotices: () => ({ data: state.notices }),
  useSupplierStockListFile: () => ({
    data: { attachment_id: 'att-1', filename: 'stock.xlsx' },
    isLoading: false,
  }),
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
    currentSearchParams = new URLSearchParams();
  });

  it('titles the record with the supplier and states started, cut-off and document', () => {
    renderView();

    expect(
      screen.getByRole('heading', { name: /CHAOZHOU JINBAICHUAN SANITARY WARE CO\., LTD/ }),
    ).toBeTruthy();
    const subtitle = screen.getByTestId('plan-subtitle').textContent ?? '';
    expect(subtitle).toContain('Started');
    expect(subtitle).toContain('SO cut-off 30/09/2026');
    expect(subtitle).toContain('Stock list 27/07/2026');
    // The state pill, not the sidebar crumb that also reads "Planning".
    expect(
      screen.getAllByText('Planning').some((el) => el.dataset.slot === 'badge'),
    ).toBe(true);
  });

  it('carries no header card and no Upload button of its own (AC-A3, AC-A12)', () => {
    renderView();

    expect(screen.queryByText('Plan until:')).toBeNull();
    expect(screen.queryByRole('button', { name: /^Upload$/i })).toBeNull();
  });

  it('offers the gear items the plan lists, in the order S1 names, and only one gear (AC-A2)', () => {
    renderView();

    expect(screen.getAllByRole('button', { name: 'Plan actions' })).toHaveLength(1);
    const menu = screen.getByTestId('menu-content');
    const labels = [
      'View uploaded list',
      'Refresh matching',
      'Refresh suggestion',
      'Copy link',
      'Download XLSX',
      'Download PDF',
      'Send to supplier',
      'Change cut-off',
      'Cancel plan',
      'Delete plan',
    ];
    const buttons = Array.from(menu.querySelectorAll('button')).map((b) => b.textContent);
    expect(buttons).toEqual(labels);
  });

  it('says why Copy link cannot act when nothing has been sent', () => {
    renderView();

    const copy = screen.getByRole('button', { name: 'Copy link' }) as HTMLButtonElement;
    expect(copy.disabled).toBe(true);
    expect(copy.getAttribute('title')).toBe('No link sent yet');
  });

  it('counts the rows that differ from the engine and saves the whole map', async () => {
    renderView();
    expect((screen.getByTestId('save-plan-edits') as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByTestId('save-plan-edits').textContent).toContain('Save (0)');

    fireEvent.click(screen.getByTestId('type-qty'));

    expect(screen.getByTestId('save-plan-edits').textContent).toContain('Save (1)');
    fireEvent.click(screen.getByTestId('save-plan-edits'));
    await waitFor(() => expect(saveEdits).toHaveBeenCalledWith({ 'row-a': 4000 }));
  });

  it('saves before it sends, so the document cannot disagree with the screen', async () => {
    renderView();
    fireEvent.click(screen.getByTestId('type-qty'));

    fireEvent.click(screen.getByRole('button', { name: 'Send to supplier' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Send' }));

    await waitFor(() => expect(saveEdits).toHaveBeenCalledWith({ 'row-a': 4000 }));
    await waitFor(() =>
      expect(sendRequest).toHaveBeenCalledWith(
        expect.objectContaining({
          planId: 'plan-1',
          lines: [{ product_id: 'prod-a', qty: 4000 }],
        }),
      ),
    );
  });

  it('a Save that fails aborts the send rather than sending the old quantities', async () => {
    // The await had no catch: the rejection went unhandled and the request went out anyway,
    // carrying quantities the plan does not hold - the one disagreement between the document
    // and the screen the save-first rule exists to prevent.
    state.saveFails = true;
    renderView();
    fireEvent.click(screen.getByTestId('type-qty'));

    fireEvent.click(screen.getByRole('button', { name: 'Send to supplier' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Send' }));

    await waitFor(() => expect(saveEdits).toHaveBeenCalled());
    expect(sendRequest).not.toHaveBeenCalled();
  });

  it('asks before leaving with unsaved quantities, and leaves once confirmed', async () => {
    renderView();
    fireEvent.click(screen.getByTestId('type-qty'));

    fireEvent.click(screen.getByTestId('back-to-plans'));

    expect(await screen.findByText('Leave without saving?')).toBeTruthy();
    expect(push).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Leave' }));
    await waitFor(() => expect(push).toHaveBeenCalledWith('/scm/loading-plan'));
  });

  it('goes straight back when nothing is unsaved', async () => {
    renderView();

    fireEvent.click(screen.getByTestId('back-to-plans'));

    await waitFor(() => expect(push).toHaveBeenCalledWith('/scm/loading-plan'));
    expect(screen.queryByText('Leave without saving?')).toBeNull();
  });

  it('asks before a refresh drops the typed quantities (AC-A16)', async () => {
    renderView();
    fireEvent.click(screen.getByTestId('type-qty'));

    fireEvent.click(screen.getByRole('button', { name: 'Refresh suggestion' }));

    expect(await screen.findByText('Drop your 1 typed quantity?')).toBeTruthy();
    expect(refetchBuild).not.toHaveBeenCalled();
  });

  it('refreshes without asking when nothing was typed', () => {
    renderView();

    fireEvent.click(screen.getByRole('button', { name: 'Refresh suggestion' }));

    expect(refetchBuild).toHaveBeenCalled();
  });

  it('a cancelled plan is read-only, and Save and Send say why (AC-A8)', () => {
    state.plan = { ...PLAN, status: 'cancelled', cancelled_at: '2026-08-27T15:00:00' };

    renderView();

    expect(screen.getByText('Cancelled')).toBeTruthy();
    const save = screen.getByTestId('save-plan-edits') as HTMLButtonElement;
    const send = screen.getByRole('button', { name: 'Send to supplier' }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    expect(send.disabled).toBe(true);
    expect(send.getAttribute('title')).toBe('This plan is cancelled.');
    expect(
      screen.getByTestId('container-request-section').getAttribute('data-readonly'),
    ).toBe('true');
  });

  it('a sent plan cannot be deleted from the gear either (Q5)', () => {
    state.plan = { ...PLAN, status: 'sent', sent_at: '2026-08-27T14:40:00' };

    renderView();

    const del = screen.getByRole('button', { name: 'Delete plan' }) as HTMLButtonElement;
    expect(del.disabled).toBe(true);
    expect(del.getAttribute('title')).toBe('Sent plans are cancelled, not deleted');
  });

  it('changes the cut-off on the plan rather than starting a second one', async () => {
    renderView();

    fireEvent.click(screen.getByRole('button', { name: 'Change cut-off' }));
    const input = await screen.findByLabelText('Sales order cut-off');
    fireEvent.change(input, { target: { value: '2026-10-31' } });
    fireEvent.click(screen.getAllByRole('button', { name: 'Save cut-off' })[0]);

    await waitFor(() =>
      expect(changeCutOff).toHaveBeenCalledWith('2026-10-31', expect.anything()),
    );
  });
});

describe('LoadingPlanView, measured against what is SAVED', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    state.plan = { ...PLAN, line_edits: { 'row-a': 4000 } };
    // What the server sends back once that edit is saved: the engine still says 4242.
    state.rows = [{ ...ENGINE_ROW, suggested_qty: 4000 }];
    state.saveFails = false;
    state.unmatchedCodes = [];
    state.notices = [];
    currentSearchParams = new URLSearchParams();
  });

  it('a saved edit is not something to save again', () => {
    renderView();

    const save = screen.getByTestId('save-plan-edits') as HTMLButtonElement;
    expect(save.textContent).toContain('Save (0)');
    expect(save.disabled).toBe(true);
  });

  it('typing a quantity back to the engine figure is a change, and clears the row', async () => {
    renderView();

    fireEvent.click(screen.getByTestId('type-engine-qty'));

    const save = screen.getByTestId('save-plan-edits') as HTMLButtonElement;
    expect(save.textContent).toContain('Save (1)');
    expect(save.disabled).toBe(false);
    fireEvent.click(save);
    await waitFor(() => expect(saveEdits).toHaveBeenCalledWith({}));
  });

  it('asks before leaving with a cleared quantity, and says what would be lost', async () => {
    renderView();
    fireEvent.click(screen.getByTestId('type-engine-qty'));

    fireEvent.click(screen.getByTestId('back-to-plans'));

    expect(await screen.findByText('Leave without saving?')).toBeTruthy();
    expect(screen.getByText(/1 changed quantity is not saved yet/)).toBeTruthy();
    expect(push).not.toHaveBeenCalled();
  });
});

describe('LoadingPlanView, changing the cut-off with edits on the screen', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    state.plan = { ...PLAN };
    state.rows = [ENGINE_ROW];
    state.saveFails = false;
    state.unmatchedCodes = [];
    state.notices = [];
    currentSearchParams = new URLSearchParams();
  });

  it('asks before the new cut-off drops the typed quantities, and drops them for real', async () => {
    // The cut-off rebuilds the suggestion against a new date, so the typed quantities cannot
    // survive it any more than a Refresh - and they were left in `edits`, so the screen went
    // on showing numbers the new build never produced.
    renderView();
    fireEvent.click(screen.getByTestId('type-qty'));

    fireEvent.click(screen.getByRole('button', { name: 'Change cut-off' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Save cut-off' }));

    expect(await screen.findByText('Drop your 1 typed quantity?')).toBeTruthy();
    expect(changeCutOff).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Change the cut-off' }));

    await waitFor(() => expect(saveEdits).toHaveBeenCalledWith({}));
    await waitFor(() => expect(changeCutOff).toHaveBeenCalled());
    expect((screen.getByTestId('save-plan-edits') as HTMLButtonElement).textContent).toContain(
      'Save (0)',
    );
  });
});

/** Radix `TabsTrigger` activates on mousedown; `fireEvent.click` alone is not enough in jsdom. */
function selectTab(name: string) {
  const tab = screen.getByRole('tab', { name });
  fireEvent.mouseDown(tab, { button: 0 });
  fireEvent.click(tab);
}

describe('LoadingPlanView - the tab strip (S2, AC-B1-B4)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    state.plan = { ...PLAN };
    state.rows = [ENGINE_ROW];
    state.saveFails = false;
    state.unmatchedCodes = [];
    state.notices = [];
    currentSearchParams = new URLSearchParams();
  });

  it('renders Lines, Supplier codes and Sent, Lines active by default, with no badge at zero (AC-B1, AC-B2)', () => {
    renderView();

    expect(screen.getByRole('tab', { name: 'Lines' })).toHaveAttribute('data-state', 'active');
    expect(screen.getByRole('tab', { name: 'Supplier codes' })).toBeTruthy();
    expect(screen.getByRole('tab', { name: 'Sent' })).toBeTruthy();
    // On screen already, since Lines is the default tab.
    expect(screen.getByTestId('container-request-section')).toBeInTheDocument();
    // Neither of the other two tabs' bodies is mounted yet.
    expect(screen.queryByTestId('supplier-codes-tab')).not.toBeInTheDocument();
    expect(screen.queryByTestId('requests-sent')).not.toBeInTheDocument();
  });

  it('shows a count once there is one, on both the codes and the sent tab (AC-B1)', () => {
    state.unmatchedCodes = [{ item_code: 'A' }, { item_code: 'B' }];
    state.notices = [{ id: 'n-1', notice_type: 'container_request', channel: 'email' }];
    renderView();

    expect(screen.getByRole('tab', { name: 'Supplier codes (2)' })).toBeTruthy();
    expect(screen.getByRole('tab', { name: 'Sent (1)' })).toBeTruthy();
  });

  it('clicking Supplier codes writes ?tab=codes (AC-B2)', () => {
    renderView();

    selectTab('Supplier codes');

    expect(replace).toHaveBeenCalledWith('/scm/loading-plan/plan-1?tab=codes', { scroll: false });
  });

  it('clicking Lines from another tab clears ?tab= rather than writing ?tab=lines', () => {
    currentSearchParams = new URLSearchParams('tab=sent');
    renderView();

    selectTab('Lines');

    expect(replace).toHaveBeenCalledWith('/scm/loading-plan/plan-1', { scroll: false });
  });

  // `Tabs` is controlled by the URL (`activeTab`, derived from `?tab=`); the mocked router
  // does not actually navigate, so these preset `?tab=` before mount rather than click and
  // expect the same jsdom render to reflow - exactly how `LoadingPlanView` itself reads a
  // deep link or a reload, and the click tests above already prove the write half survives.
  it('?tab=codes lands on the Supplier codes tab and shows the tab body (AC-B2)', () => {
    state.unmatchedCodes = [{ item_code: 'A' }];
    currentSearchParams = new URLSearchParams('tab=codes');
    renderView();

    expect(screen.getByRole('tab', { name: 'Supplier codes (1)' })).toHaveAttribute(
      'data-state',
      'active',
    );
    expect(screen.getByTestId('supplier-codes-tab')).toBeInTheDocument();
    expect(screen.queryByTestId('container-request-section')).not.toBeInTheDocument();
  });

  // The exact empty-state copy ("Every code on file is matched") is `SupplierCodesTab`'s own
  // (SupplierCodesTab.test.tsx, AC-B4/AC-C3): the tab now mounts unconditionally so the
  // Remembered group is reachable even once the queue is answered down to nothing, so what
  // this level of the record owns is only that the tab keeps mounting at zero.
  it('the Supplier codes tab still mounts its body with nothing left to answer (AC-B4)', () => {
    currentSearchParams = new URLSearchParams('tab=codes');
    renderView();

    expect(screen.getByTestId('supplier-codes-tab')).toBeInTheDocument();
  });

  it('an empty Sent tab says nothing has gone out yet and offers Send (AC-B4)', async () => {
    currentSearchParams = new URLSearchParams('tab=sent');
    renderView();

    const sentCard = screen.getByTestId('requests-sent');
    expect(within(sentCard).getByText('Nothing sent yet.')).toBeInTheDocument();
    fireEvent.click(within(sentCard).getByRole('button', { name: /send to supplier/i }));
    // The same Send dialog the gear opens - the Sent tab's own trigger, not a second flow.
    expect(await screen.findByRole('button', { name: 'Send' })).toBeTruthy();
  });

  it('a reload on ?tab=sent lands on the Sent tab, not Lines (AC-B2)', () => {
    currentSearchParams = new URLSearchParams('tab=sent');
    renderView();

    expect(screen.getByRole('tab', { name: 'Sent' })).toHaveAttribute('data-state', 'active');
    expect(screen.getByTestId('requests-sent')).toBeInTheDocument();
    expect(screen.queryByTestId('container-request-section')).not.toBeInTheDocument();
  });
});
