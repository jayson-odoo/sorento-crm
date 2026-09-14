/**
 * S7 - the PI Lines tab answers a supplier code from ONE always-on Product dropdown
 * (`PLAN-scm-ui-feedback-14sep.md`, J5, ruling R7).
 *
 * TEST-FIRST. At the time this file is written the Lines grid still carries a separate
 * `Match` column with Matched / Not in catalogue badges and a Match / Change / Forget button
 * row that opens `MatchToProductDialog`, and the Product select exists only in EDIT mode and
 * searches products alone. Every test asserting the new control is expected to be red until
 * S7 lands.
 *
 * Why one control (owner screenshots, 14 Sep): the Product cell and the Match column are the
 * same decision through two doors, and the edit-mode Save path already writes the very alias
 * the dialog writes (`_remember_line_match`). The loading plan's Supplier codes cell answers
 * the identical question with a single select, so this page borrows it whole:
 * `fetchProductOrSetOptions` + `renderProductOrSetOption`, pick POSTs the alias at once, and
 * clearing it starts the reversible forget countdown.
 *
 * Mock surface copied from `ProformaInvoiceDetail.test.tsx`, with three changes it needs and
 * that file does not: the permission hook is switchable (AC-7.7), the match mutation's
 * `isPending` is switchable (AC-7.3), and `getProductSets` is mocked so the picker's set half
 * is a fixture rather than an unanswered fetch.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
/* The grace window is the server's; what this file proves is that the control parks one -
 * and, for AC-7.5, that Cancel gives the cell its picker back. So the service is stood in
 * for rather than stubbed: it parks what it is asked to park, answers `current` off the
 * same store, and forgets it on cancel. A fixed resolve cannot show a countdown at all -
 * `useDeferredAction` ignores a parked action whose `action_key` is not the one it asked
 * for. */
const parkedActions = new Map<string, Record<string, unknown>>();
const createPendingAction = vi.fn();
const cancelPendingAction = vi.fn();
const getCurrentPendingAction = vi.fn();
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...args: unknown[]) => createPendingAction(...args),
  cancelPendingAction: (...args: unknown[]) => cancelPendingAction(...args),
  getCurrentPendingAction: (...args: unknown[]) => getCurrentPendingAction(...args),
}));

/** A naive-UTC timestamp `offsetMs` from now, the way the backend writes them. */
function serverTime(offsetMs: number): string {
  return new Date(Date.now() + offsetMs).toISOString().replace(/\.\d+Z$/, '');
}

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ProformaInvoiceDetail as ProformaInvoiceDetailData } from '../../../services/proformaInvoiceService';

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
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});

vi.mock('@/components/common/ListPager', () => ({ __esModule: true, default: () => null }));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

// `scm.proforma_invoice.upload` is the slug the permission registry actually holds
// (`permission_registry.py:704`, seeded by migration 375) and the one this page has always
// gated adjusting on. The UAC names it "adjust" in prose; there is no such permission, and
// gating on it would take the picker away from everybody.
const { perms } = vi.hoisted(() => ({ perms: { canAdjust: true, canRule: true } }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => {
    if (slug === 'scm.proforma_invoice.upload') return perms.canAdjust;
    // Writing the supplier's ruling is what the alias POST/DELETE are behind, and the
    // picker acts on both (review round 1, S4).
    if (slug === 'scm.reorder.run') return perms.canRule;
    return true;
  },
}));

const push = vi.fn();
const replace = vi.fn();
// The tab lives in the URL (S1) - a real `URLSearchParams` so `.get('tab')` and `.toString()`
// both behave, swappable per test to prove a reload lands back on the tab named in it.
let currentSearchParams = new URLSearchParams();
vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/proforma-invoices/pi-1',
  useRouter: () => ({ push, replace }),
  useSearchParams: () => currentSearchParams,
}));

// The WHOLE surface the components under test call. `ConfirmDeleteDialog` reports through
// `toast.custom`, and a mock without it threw inside react-query's own error path - which
// surfaced as an unhandled rejection that failed no test and hid any real one behind it.
vi.mock('@/lib/toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
    custom: vi.fn(),
    dismiss: vi.fn(),
  },
}));

// The line grid's product picker is server-searched; this suite is not testing the catalogue.
// A `vi.fn()` (not a bare async function) so the AC-B3/AC-B5 tests can hand back a real
// page for the ONE product being picked, without the rest of the suite caring.
const { getProductsMock } = vi.hoisted(() => ({
  getProductsMock: vi.fn().mockResolvedValue({ data: [], pagination: { total: 0 } }),
}));
vi.mock('@/app/(protected)/master-data-management/products/services/productService', () => ({
  getProducts: getProductsMock,
}));

// The picker offers our product SETS beside the products (F12, R20) - the supplier prices the
// whole WC under a code no product carries, and AC-7.4 is about picking one.
const { getProductSetsMock } = vi.hoisted(() => ({
  getProductSetsMock: vi.fn().mockResolvedValue({ data: [], pagination: { total: 0 } }),
}));
vi.mock(
  '@/app/(protected)/master-data-management/product-sets/services/productSetService',
  () => ({ getProductSets: getProductSetsMock }),
);

// The master list (AC-B4), not free text - fed to every UoM cell's SearchableSelect.
// `vi.hoisted` because the array has to exist before `vi.mock`'s own hoisting runs it: the
// real `useUOMSelectQuery` is a `useQuery` with `staleTime: Infinity`, so `data` is the SAME
// reference across renders once loaded - a fresh literal returned from the mock on every
// call would fabricate an instability the real hook does not have, and cascade into the
// Lines grid's `columns` memo recomputing (and remounting every row's `SearchableSelect`)
// on every unrelated render.
const { UOM_OPTIONS } = vi.hoisted(() => ({
  UOM_OPTIONS: [
    { id: 'u-pcs', uom_code: 'PCS', uom_name: 'Pieces' },
    { id: 'u-box', uom_code: 'BOX', uom_name: 'Box' },
    { id: 'u-set', uom_code: 'SET', uom_name: 'Set' },
  ],
}));
vi.mock('@/app/(protected)/master-data-management/shared/hooks/use-uom-select-query', () => ({
  useUOMSelectQuery: () => ({
    data: UOM_OPTIONS,
    isLoading: false,
  }),
}));

const state = {
  data: undefined as ProformaInvoiceDetailData | undefined,
  isLoading: false,
  isError: false,
};

/** AC-7.3: the select is disabled while the alias POST is in flight, so the mutation's own
 *  pending flag has to be drivable from a test. */
const { matching } = vi.hoisted(() => ({ matching: { isPending: false } }));

/** The writes, so a test can assert what the page ASKED the backend for. */
const writes = {
  matchCode: vi.fn(),
  forgetMatch: vi.fn(),
  save: vi.fn(),
  markAsRevision: vi.fn(),
  convert: vi.fn(),
};

vi.mock('../../../hooks/useProformaInvoices', () => ({
  // The pager reads the list page through the entity's shared key + fetch (S3-03).
  proformaInvoicesPagerQuery: {
    listQueryKey: () => ['scm-proforma-invoices'],
    fetchPage: async () => ({ data: [], pagination: { total: 0 } }),
  },
  // The real key-builder, not a stub: `useProformaInvoicePacking`'s queryFn reads the
  // detail query's cache through this exact key (AC-E2 fix) - a mock that dropped it
  // left the packing query's `queryFn` throwing on every fetch, silently emptying every
  // dialog/tab that reads packing rows in this suite.
  proformaInvoiceDetailQueryKey: (id: string | null) => ['scm', 'proforma-invoices', 'detail', id],
  useProformaInvoice: () => state,
  // The header's pager pulls the neighbour list through this hook - one row is not enough to
  // show a pager (RecordNavigation's `items.length < 2` guard), so it stays out of the way.
  useProformaInvoices: () => ({ data: undefined, isLoading: false }),
  useConvertProformaInvoicesToDraftShipment: () => ({
    mutateAsync: writes.convert,
    isPending: false,
  }),
  useSaveProformaInvoice: () => ({ mutateAsync: writes.save, isPending: false }),
  useMarkProformaInvoiceAsRevision: () => ({
    mutateAsync: writes.markAsRevision,
    isPending: false,
  }),
}));

vi.mock('../../../hooks/useSupplierCodeAliases', () => ({
  useMatchSupplierCode: () => ({
    mutateAsync: writes.matchCode,
    isPending: matching.isPending,
  }),
  useForgetSupplierCodeMatch: () => ({ mutateAsync: writes.forgetMatch, isPending: false }),
}));

vi.mock('../../../hooks/useFulfilment', () => ({
  useContainerSizes: () => ({
    data: [
      { id: 'size-40hq', code: '40HQ', label: '40ft high cube', cbm: 65, is_default: true },
      { id: 'size-20gp', code: '20GP', label: '20ft standard', cbm: 28, is_default: false },
    ],
    isLoading: false,
  }),
  // The Packing tab's "Attach packing list" mounts `SupplierDocumentsUploadDialog`
  // (S2), whose self-serve supplier picker reads this hook - irrelevant here since the
  // dialog is opened with `supplierId` already fixed to the invoice's own.
  useFulfilmentSuppliers: () => ({ data: [], isLoading: false }),
}));

import { pendingEntityStore } from '@/lib/pending-entity-store';

import { ProformaInvoiceDetail } from './ProformaInvoiceDetail';

function detail(over: Partial<ProformaInvoiceDetailData> = {}): ProformaInvoiceDetailData {
  return {
    id: 'pi-1',
    supplier_id: 'sup-1',
    supplier_code: 'KAILU',
    supplier_name: 'Kailu Hardware Factory',
    pi_number: 'PI-2026-001',
    // Ours and theirs: `pi_number` is the number we minted, `supplier_ref` the one the
    // factory printed on the document (S1, AC-A2/A5).
    supplier_ref: 'KL20260801',
    invoice_date: '2026-08-01',
    currency: 'CNY',
    container_no: 'TEMU1234567',
    seal_no: 'WHA4528193',
    consignee: 'SORENTO SDN BHD',
    bl_no: 'BL-991',
    total_amount: 1000,
    line_count: 1,
    source_ref: 'proforma.xlsx',
    block_index: 0,
    uploaded_by: 'Ms Tee',
    created_at: '2026-08-01T02:00:00',
    updated_at: '2026-08-01T02:00:00',
    total_cbm: 69.36,
    unmeasured_lines: 0,
    status: 'current',
    revision_no: 1,
    revision_count: 1,
    adjusted_by: null,
    adjusted_at: null,
    is_adjusted: false,
    placement: 'not_converted',
    placed_qty: 0,
    total_qty: 10,
    remaining_qty: 10,
    packing_lists: [],
    lines: [
      {
        id: 'line-1',
        line_no: 1,
        row_number: 2,
        item_code: 'ITEM-1',
        description: 'Widget',
        qty: 10,
        uom: 'PCS',
        unit_price: 100,
        amount: 1000,
        po_ref: 'PO-1',
        remark: null,
        cartons: 10,
        cbm_per_unit: 0.17,
        cbm_total: 1.7,
        net_weight: 40,
        gross_weight: 50,
        supplier_qty: 10,
        supplier_unit_price: 100,
        placed_qty: 0,
        remaining_qty: 10,
        packing_lists: [],
        matched_by: null,
        match_source: null,
        match_id: null,
        product_id: 'prod-item-1',
        product_set_id: null,
        product_code: 'ITEM-1',
        set_code: null,
        matched: true,
        shipment_id: null,
        shipment_number: null,
        unmatched_reason: null,
      },
    ],
    converted_shipments: [],
    revisions: [
      {
        id: 'pi-1',
        pi_number: 'PI-2026-001',
        revision_no: 1,
        status: 'current',
        invoice_date: '2026-08-01',
        total_amount: 1000,
        line_count: 1,
      },
    ],
    revision_of_pi_number: null,
    diff: null,
    ...over,
  };
}

/** The last render's `rerender`, so `openTab` can force a re-read of the mocked URL - same
 *  trick `renderDetail`'s own `refresh` uses. */
let currentRerender: (() => void) | null = null;

function renderDetail() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const tree = () => (
    <QueryClientProvider client={qc}>
      <ProformaInvoiceDetail id="pi-1" />
    </QueryClientProvider>
  );
  const view = render(tree());
  currentRerender = () => view.rerender(tree());
  // The detail hook is mocked, so a write's invalidation cannot be observed the usual way.
  // `refresh` replays what the refetch would do.
  return { ...view, refresh: () => view.rerender(tree()) };
}

/** Radix opens a dropdown on POINTERDOWN, not on click - a plain click is a silent no-op. */
function openActions() {
  fireEvent.pointerDown(screen.getByRole('button', { name: /more actions/i }), {
    button: 0,
    ctrlKey: false,
    pointerType: 'mouse',
  });
}

const TAB_PARAM: Record<'General' | 'Lines' | 'Revisions' | 'Packing lists', string | null> = {
  General: null,
  Lines: 'lines',
  Revisions: 'revisions',
  'Packing lists': 'packing-lists',
};

/**
 * The tab now lives in the URL (S1), not local state, so a click's own re-render depends on
 * the mocked router actually navigating - it doesn't. This sets `?tab=` the way the click's
 * `router.replace` would have written it and re-renders, exactly as `LoadingPlanView.test.tsx`
 * does for the same reason. The writing half of the click itself is pinned separately, in
 * "ProformaInvoiceDetail - the tab lives in the URL (S1)" below.
 */
function openTab(name: 'General' | 'Lines' | 'Revisions' | 'Packing lists') {
  const value = TAB_PARAM[name];
  currentSearchParams = new URLSearchParams(value ? `tab=${value}` : '');
  currentRerender?.();
}

/** Open the gear menu and press Edit, which is where editing starts from now. */
function beginEdit() {
  openActions();
  fireEvent.click(screen.getByRole('menuitem', { name: /^edit$/i }));
}

function lastSavePayload() {
  return writes.save.mock.calls[writes.save.mock.calls.length - 1][0] as {
    pi_number?: string;
    lines?: Array<Record<string, unknown>>;
  };
}

beforeEach(() => {
  state.data = undefined;
  state.isLoading = false;
  state.isError = false;
  push.mockReset();
  replace.mockReset();
  currentSearchParams = new URLSearchParams();
  currentRerender = null;
  writes.save.mockReset().mockResolvedValue(undefined);
  writes.forgetMatch.mockReset().mockResolvedValue(undefined);
  writes.markAsRevision.mockReset().mockResolvedValue(undefined);
  getProductsMock.mockReset().mockResolvedValue({ data: [], pagination: { total: 0 } });
  getProductSetsMock.mockReset().mockResolvedValue({ data: [], pagination: { total: 0 } });
  writes.matchCode.mockReset().mockResolvedValue({
    id: 'alias-new',
    supplier_code: 'ITEM-1',
    product_id: 'prod-99',
    product_code: 'NEWCODE',
    product_set_id: null,
    set_code: null,
    set_name: null,
    source: 'manual',
    matched_by: 'manual',
    rebound_stock_rows: 0,
    rebound_invoice_lines: 1,
  });
  parkedActions.clear();
  createPendingAction.mockReset().mockImplementation(
    async ({
      actionKey,
      entityType,
      entityId,
    }: {
      actionKey: string;
      entityType: string;
      entityId: string;
    }) => {
      const action = {
        id: `pa-${entityId}`,
        action_key: actionKey,
        entity_type: entityType,
        entity_id: entityId,
        commit_at: serverTime(5_000),
        window_seconds: 5,
      };
      parkedActions.set(entityId, action);
      return action;
    },
  );
  cancelPendingAction.mockReset().mockImplementation(async (id: string) => {
    for (const [entityId, action] of parkedActions) {
      if (action.id === id) parkedActions.delete(entityId);
    }
  });
  getCurrentPendingAction
    .mockReset()
    .mockImplementation(async (_entityType: string, entityId: string) => ({
      pending: parkedActions.get(entityId) ?? null,
      last_outcome: null,
    }));
  pendingEntityStore.reset();
  matching.isPending = false;
  perms.canAdjust = true;
  perms.canRule = true;
});

/** The Product select is the first combobox in a line's row, the UoM select the second -
 *  column order (`item_code, product, description, qty, uom, ...`) puts Product ahead of
 *  UoM, and only the UoM select carries its own accessible name. */
function lineRow(itemCodeAriaLabel: string): HTMLElement {
  return screen.getByLabelText(itemCodeAriaLabel).closest('tr') as HTMLElement;
}

/** A line's row in READ mode, where no input carries an accessible name. */
function readRow(itemCode: string): HTMLElement {
  return screen.getByText(itemCode).closest('tr') as HTMLElement;
}

/** The Product select on a read-mode row: the only combobox the cell draws. */
function productSelect(itemCode: string): HTMLElement {
  return within(readRow(itemCode)).getAllByRole('combobox')[0];
}

/** One catalogue page and one set page, the picker's two halves. */
function offerCatalogue() {
  getProductsMock.mockResolvedValue({
    data: [{ id: 'prod-99', product_code: 'NEWCODE', product_name: 'New product' }],
    pagination: { total: 1 },
  });
  getProductSetsMock.mockResolvedValue({
    data: [{ id: 'set-7', set_code: 'CWC605-RL', name: 'Close-coupled WC' }],
    pagination: { total: 1 },
  });
}

/** The supplier's own spelling, DIFFERENT from the code it is bound to - which is the whole
 *  point of an alias, and what lets a test say which of the two a cell is printing. */
const SUPPLIER_CODE = 'JBC-8366';
const OUR_CODE = 'SRTWC8366-RL';

/** A coded line that is already bound, which is the common case on a real invoice. */
function codedLine(over: Record<string, unknown> = {}) {
  return {
    ...detail().lines[0],
    item_code: SUPPLIER_CODE,
    product_code: OUR_CODE,
    ...over,
  };
}

/** The invoice as these tests hold it: one coded, bound line. */
function coded(over: Record<string, unknown> = {}) {
  return detail({ lines: [codedLine(over)] });
}

// --------------------------------------------------------------------------- AC-7.1

describe('ProformaInvoiceDetail - the Match column is gone (AC-7.1)', () => {
  it('draws no Match column and no Matched badge on a bound line', () => {
    state.data = coded();
    renderDetail();
    openTab('Lines');

    expect(screen.queryByRole('columnheader', { name: 'Match' })).toBeNull();
    expect(screen.queryByText('Matched')).toBeNull();
  });

  it('draws no "Not in catalogue" badge and no Match button on an unbound line', () => {
    state.data = coded({
      matched: false,
      product_id: null,
      product_code: null,
      match_id: null,
      match_source: null,
      unmatched_reason: "No catalogue product matches this line's item code.",
    });
    renderDetail();
    openTab('Lines');

    expect(screen.queryByText('Not in catalogue')).toBeNull();
    expect(screen.queryByRole('button', { name: /match to product/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /^change$/i })).toBeNull();
  });
});

// --------------------------------------------------------------------------- AC-7.2

describe('ProformaInvoiceDetail - the Product cell is a picker in READ mode (AC-7.2)', () => {
  it('offers the picker without Edit, and shows the current match as its code', async () => {
    offerCatalogue();
    state.data = coded();
    renderDetail();
    openTab('Lines');

    const select = productSelect(SUPPLIER_CODE);
    expect(select).toBeInTheDocument();
    // The CODE it is bound to, not the supplier's own spelling beside it.
    expect(select.textContent).toContain(OUR_CODE);
  });

  it('says "Search a product or set" on a line that is bound to nothing', () => {
    offerCatalogue();
    state.data = coded({ product_id: null, product_code: null, matched: false, match_id: null });
    renderDetail();
    openTab('Lines');

    expect(within(readRow(SUPPLIER_CODE)).getByText('Search a product or set')).toBeInTheDocument();
  });

  it('lists the SETS first, badged, then the products', async () => {
    offerCatalogue();
    state.data = coded();
    renderDetail();
    openTab('Lines');

    fireEvent.click(productSelect(SUPPLIER_CODE));

    const options = await screen.findAllByRole('option');
    expect(options.map((o) => o.textContent)).toEqual([
      expect.stringContaining('CWC605-RL - Close-coupled WC'),
      expect.stringContaining('NEWCODE - New product'),
    ]);
    expect(options[0].textContent).toContain('Set');
  });
});

// --------------------------------------------------------------------------- AC-7.3

describe('ProformaInvoiceDetail - a pick writes the alias at once (AC-7.3)', () => {
  it('POSTs the alias with no Edit and no Save', async () => {
    offerCatalogue();
    state.data = coded();
    renderDetail();
    openTab('Lines');

    fireEvent.click(productSelect(SUPPLIER_CODE));
    fireEvent.click(await screen.findByRole('option', { name: /NEWCODE - New product/ }));

    await waitFor(() => expect(writes.matchCode).toHaveBeenCalledTimes(1));
    expect(writes.matchCode).toHaveBeenCalledWith({
      supplier_id: 'sup-1',
      supplier_code: SUPPLIER_CODE,
      product_id: 'prod-99',
    });
    // The draft save path is not involved at all.
    expect(writes.save).not.toHaveBeenCalled();
  });

  it('disables the select while the request is in flight', () => {
    offerCatalogue();
    matching.isPending = true;
    state.data = coded();
    renderDetail();
    openTab('Lines');

    expect(productSelect(SUPPLIER_CODE)).toBeDisabled();
  });
});

// --------------------------------------------------------------------------- AC-7.4

describe('ProformaInvoiceDetail - picking a set (AC-7.4)', () => {
  it('sends product_set_id, not product_id', async () => {
    offerCatalogue();
    state.data = coded();
    renderDetail();
    openTab('Lines');

    fireEvent.click(productSelect(SUPPLIER_CODE));
    fireEvent.click(await screen.findByRole('option', { name: /CWC605-RL - Close-coupled WC/ }));

    await waitFor(() => expect(writes.matchCode).toHaveBeenCalledTimes(1));
    expect(writes.matchCode).toHaveBeenCalledWith({
      supplier_id: 'sup-1',
      supplier_code: SUPPLIER_CODE,
      product_set_id: 'set-7',
    });
  });
});

// --------------------------------------------------------------------------- AC-7.5

describe('ProformaInvoiceDetail - clearing the pick forgets the ruling (AC-7.5)', () => {
  it('parks the reversible forget countdown against the alias', async () => {
    offerCatalogue();
    state.data = coded({ match_id: 'alias-1', match_source: 'manual' });
    renderDetail();
    openTab('Lines');

    fireEvent.pointerDown(
      within(readRow(SUPPLIER_CODE)).getByRole('button', { name: 'Clear selection' }),
    );

    await waitFor(() => expect(createPendingAction).toHaveBeenCalledTimes(1));
    expect(createPendingAction).toHaveBeenCalledWith(
      expect.objectContaining({
        actionKey: 'supplier_code_alias.forget',
        entityType: 'supplier_code_alias',
        entityId: 'alias-1',
      }),
    );
  });

  it('gives the picker back when the countdown is cancelled', async () => {
    offerCatalogue();
    state.data = coded({ match_id: 'alias-1', match_source: 'manual' });
    renderDetail();
    openTab('Lines');

    fireEvent.pointerDown(
      within(readRow(SUPPLIER_CODE)).getByRole('button', { name: 'Clear selection' }),
    );

    // The countdown takes the cell the picker was in, with its own Cancel (AC-7.5).
    const cell = await screen.findByTestId('deferred-countdown');
    expect(within(readRow(SUPPLIER_CODE)).getByTestId('deferred-countdown')).toBe(cell);

    fireEvent.click(within(cell).getByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(cancelPendingAction).toHaveBeenCalledWith('pa-alias-1'));
    // And the ruling is still on the line: the cell reads as the picker again, showing
    // the code it was bound to - not as the blank it showed while the target was held
    // after the window had closed.
    await waitFor(() =>
      expect(screen.queryByTestId('deferred-countdown')).not.toBeInTheDocument(),
    );
    expect(productSelect(SUPPLIER_CODE)).toHaveTextContent(OUR_CODE);
  });

  it('offers no clear on a line with no remembered ruling behind it', () => {
    offerCatalogue();
    state.data = coded({
      match_id: null,
      match_source: null,
      product_code: null,
      matched: false,
    });
    renderDetail();
    openTab('Lines');

    expect(
      within(readRow(SUPPLIER_CODE)).queryByRole('button', { name: 'Clear selection' }),
    ).toBeNull();
  });
});

// S1 (review round 1): the same pick, made from an edit session.

describe('ProformaInvoiceDetail - a pick made while editing (AC-7.3)', () => {
  it('shows the new code at once and saves the line agreeing with the server', async () => {
    offerCatalogue();
    state.data = coded();
    renderDetail();
    beginEdit();
    openTab('Lines');

    const combo = within(lineRow('Item code for line 1')).getAllByRole('combobox')[0];
    fireEvent.click(combo);
    fireEvent.click(await screen.findByRole('option', { name: /NEWCODE - New product/ }));

    await waitFor(() => expect(writes.matchCode).toHaveBeenCalledTimes(1));
    // The draft renders the edit session, and no refetch touches it - without the patch
    // the cell went on showing the old code until the edit was cancelled.
    await waitFor(() =>
      expect(
        within(lineRow('Item code for line 1')).getAllByRole('combobox')[0],
      ).toHaveTextContent('NEWCODE'),
    );

    fireEvent.click(screen.getByRole('button', { name: /^Save proforma invoice$/i }));

    await waitFor(() => expect(writes.save).toHaveBeenCalledTimes(1));
    // Save writes back what the server already holds, rather than reverting it.
    expect(lastSavePayload().lines?.[0]?.product_id).toBe('prod-99');
    // The set binding was null before the pick and is null after it, so the key is left
    // out of the payload entirely - the AC-B3 rule that stops a plain save unbinding a
    // line still holds over a pick made this way.
    expect(lastSavePayload().lines?.[0]).not.toHaveProperty('product_set_id');
  });
});

// --------------------------------------------------------------------------- AC-7.6

describe('ProformaInvoiceDetail - an operator-added line keeps the draft (AC-7.6)', () => {
  const blank = () =>
    coded({
      id: 'line-9',
      item_code: '',
      description: 'Hand written line',
      product_id: null,
      product_code: null,
      match_id: null,
      match_source: null,
      matched: false,
    });

  it('shows no picker in read mode for a line with no code', () => {
    offerCatalogue();
    state.data = blank();
    renderDetail();
    openTab('Lines');

    const row = screen.getByText('Hand written line').closest('tr') as HTMLElement;
    expect(within(row).queryAllByRole('combobox')).toHaveLength(0);
  });

  it('names the SET by its own code when one is picked, and saves the set binding', async () => {
    offerCatalogue();
    state.data = blank();
    renderDetail();
    beginEdit();
    openTab('Lines');

    const combo = within(lineRow('Item code for line 1')).getAllByRole('combobox')[0];
    fireEvent.click(combo);
    fireEvent.click(await screen.findByRole('option', { name: /CWC605-RL - Close-coupled WC/ }));

    // The set's own code, not whatever product code the row carried before it - the cell
    // has to survive a remount reading the same thing.
    await waitFor(() =>
      expect(
        within(lineRow('Item code for line 1')).getAllByRole('combobox')[0],
      ).toHaveTextContent('CWC605-RL'),
    );

    fireEvent.click(screen.getByRole('button', { name: /^Save proforma invoice$/i }));

    await waitFor(() => expect(writes.save).toHaveBeenCalledTimes(1));
    expect(lastSavePayload().lines?.[0]?.product_set_id).toBe('set-7');
    // Never bound to a product, so that key is left out rather than sent as null.
    expect(lastSavePayload().lines?.[0]).not.toHaveProperty('product_id');
    // The line carries the set's code now, which is what makes it saveable at all.
    expect(lastSavePayload().lines?.[0]?.item_code).toBe('CWC605-RL');
    expect(writes.matchCode).not.toHaveBeenCalled();
  });

  it('patches the draft in edit mode and persists it on Save, writing no alias', async () => {
    offerCatalogue();
    state.data = blank();
    renderDetail();
    beginEdit();
    openTab('Lines');

    const productCombo = within(lineRow('Item code for line 1')).getAllByRole('combobox')[0];
    fireEvent.click(productCombo);
    fireEvent.click(await screen.findByRole('option', { name: /NEWCODE - New product/ }));
    fireEvent.click(screen.getByRole('button', { name: /^Save proforma invoice$/i }));

    await waitFor(() => expect(writes.save).toHaveBeenCalledTimes(1));
    expect(lastSavePayload().lines?.[0]?.product_id).toBe('prod-99');
    expect(writes.matchCode).not.toHaveBeenCalled();
  });
});

// --------------------------------------------------------------------------- AC-7.7

describe('ProformaInvoiceDetail - a reader who cannot adjust (AC-7.7)', () => {
  it('sees the product code as text where the buyer sees a picker', () => {
    offerCatalogue();
    state.data = coded();

    // The buyer, for contrast - without this half the assertion below would pass on the
    // current code, where nobody gets a picker in read mode at all.
    const buyer = renderDetail();
    openTab('Lines');
    expect(within(readRow(SUPPLIER_CODE)).getAllByRole('combobox').length).toBe(1);
    buyer.unmount();

    perms.canAdjust = false;
    currentSearchParams = new URLSearchParams('tab=lines');
    renderDetail();

    const row = readRow(SUPPLIER_CODE);
    expect(within(row).queryAllByRole('combobox')).toHaveLength(0);
    expect(within(row).getAllByText(OUR_CODE).length).toBeGreaterThanOrEqual(1);
  });

  it('sees the code as text without the permission the RULING itself is behind', () => {
    // The alias POST and DELETE sit behind `scm.reorder.run`, so a reader who may adjust
    // the invoice but may not write the supplier's memory would have got a select that
    // 403s on the pick (S4, review round 1).
    offerCatalogue();
    state.data = coded();
    perms.canRule = false;
    currentSearchParams = new URLSearchParams('tab=lines');
    renderDetail();

    const row = readRow(SUPPLIER_CODE);
    expect(within(row).queryAllByRole('combobox')).toHaveLength(0);
    expect(within(row).getAllByText(OUR_CODE).length).toBeGreaterThanOrEqual(1);
  });
});
