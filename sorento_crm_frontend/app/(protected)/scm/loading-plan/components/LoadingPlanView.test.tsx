/**
 * The loading plan RECORD (part 4, R5 / R6 - AC-A12, A13, A14, A15, A16, and the read-only
 * half of A8).
 *
 * What this suite pins is the toolbar, because that is what the captain's 27 Aug ruling
 * reshaped: the supplier is the title, the subtitle states started / cut-off / document, the
 * status is a badge, and the right cluster reads [gear] [Save (N)] [Send to supplier] [Back]
 * with the gear FIRST. Save counts the rows that differ from the engine's own answer, Send
 * saves before it sends, leaving with unsaved edits asks, and a cancelled plan can do neither.
 *
 * The ranked grid inside it is `ContainerRequestSection.test.tsx`; the popup that starts a
 * plan is `PlanContainerDialog.test.tsx`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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
vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/loading-plan/plan-1',
  useRouter: () => ({ push, replace: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
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

// The queue panel has its own suite; here it only has to prove it mounted.
vi.mock('./UnmatchedSupplierCodesPanel', () => ({
  UnmatchedSupplierCodesPanel: () => <div data-testid="unmatched-panel" />,
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
};

const saveEdits = vi.fn();
const sendRequest = vi.fn();
const cancelPlan = vi.fn();
const changeCutOff = vi.fn();
const refetchBuild = vi.fn();

vi.mock('../../hooks/useFulfilment', () => ({
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
  useSupplierNotices: () => ({ data: [] }),
  useSupplierStockListFile: () => ({
    data: { attachment_id: 'att-1', filename: 'stock.xlsx' },
    isLoading: false,
  }),
}));

vi.mock('../../hooks/useSupplierCodeAliases', () => ({
  useRematchSupplierCodes: () => ({ mutate: vi.fn(), isPending: false }),
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
    expect(screen.getByText('Planning')).toBeTruthy();
  });

  it('carries no header card and no Upload button of its own (AC-A3, AC-A12)', () => {
    renderView();

    expect(screen.queryByText('Plan until:')).toBeNull();
    expect(screen.queryByRole('button', { name: /^Upload$/i })).toBeNull();
  });

  it('offers the gear items the plan lists, and only one gear', () => {
    renderView();

    expect(screen.getAllByRole('button', { name: 'Plan actions' })).toHaveLength(1);
    for (const item of [
      'View uploaded list',
      'Refresh matching',
      'Refresh suggestion',
      'Copy link',
      'Download XLSX',
      'Download PDF',
      'Change cut-off',
      'Cancel plan',
      'Delete plan',
    ]) {
      expect(screen.getByRole('button', { name: item })).toBeTruthy();
    }
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

    fireEvent.click(screen.getByTestId('send-to-supplier'));
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
    const send = screen.getByTestId('send-to-supplier') as HTMLButtonElement;
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
    fireEvent.click(screen.getAllByRole('button', { name: 'Save' })[0]);

    await waitFor(() =>
      expect(changeCutOff).toHaveBeenCalledWith('2026-10-31', expect.anything()),
    );
  });
});
