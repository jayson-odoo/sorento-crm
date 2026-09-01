/**
 * SPODocumentDetail - the SPO document form view (PLAN-spo-investigation-grid.md
 * S2; UAC AC-2, AC-6, AC-7).
 *
 *   - AC-2/AC-6: the header status pill words Outstanding GREEN.
 *   - AC-6: the Lines tab's Plan badge renders all four planning_span states
 *     (In plan / Pool / Off / No location).
 *   - AC-7: lines matching the URL's product/warehouse filter arrive
 *     highlighted while every line on the document stays visible.
 *
 * `useSPODocument` is mocked so these tests pin RENDERING, never a restated
 * copy of the fetch/URL-encoding logic (that is `spoDocumentService.test.ts`'s
 * and `useSPODocuments`'s job).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, within, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}
Element.prototype.scrollIntoView = vi.fn();

let searchParams = new URLSearchParams();
const routerPush = vi.fn();
const routerReplace = vi.fn();
vi.mock('@/components/common/ListPager', () => ({ __esModule: true, default: () => null }));

vi.mock('next/navigation', () => ({
  usePathname: () => '/procurement-management/spo-allocations/SPO-2026%2F08-0061',
  useRouter: () => ({ push: routerPush, replace: routerReplace }),
  useSearchParams: () => searchParams,
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const useSPODocument = vi.fn();
vi.mock('../hooks/useSPODocuments', () => ({
  useSPODocument: (...a: unknown[]) => useSPODocument(...a),
  spoDocumentsPagerQuery: { listQueryKey: () => ['spo-doc-pager'], fetchPage: async () => ({ data: [], pagination: { total: 0 } }) },
}));

vi.mock(
  '@/app/(protected)/inventory-management/warehouses/services/warehouseService',
  () => ({ getWarehouses: vi.fn(async () => ({ data: [], pagination: { total: 0 } })) }),
);

// Server search back-ends for the Lines-tab editors (UAT AC-24 parts 1/3) - only
// called once a picker's popover is OPENED, which none of these tests do; mocked
// anyway so nothing here can make a real network call.
vi.mock(
  '@/app/(protected)/master-data-management/products/services/productService',
  () => ({ getProducts: vi.fn(async () => ({ data: [], pagination: { total: 0 } })) }),
);
vi.mock('../../suppliers/services/supplierService', () => ({
  searchSuppliersForSelect: vi.fn(async () => []),
}));

// Save (review B2) calls the REAL per-line mutations - `updateSPOAllocation` /
// `deleteSPOAllocation` have their own service-level tests, so only the WIRING is
// pinned here: which id, which fields, which line goes to which mutation.
const updateMutateAsync = vi.fn();
const deleteMutateAsync = vi.fn();
vi.mock('../hooks/useSPOAllocations', () => ({
  useUpdateSPOAllocation: () => ({ mutateAsync: updateMutateAsync }),
  useDeleteSPOAllocation: () => ({ mutateAsync: deleteMutateAsync }),
}));

// The engine (park/countdown/commit) is `hooks/useDeferredAction.test.tsx`'s job -
// this only pins that the gear's Delete document (UAT AC-26) wires the right
// action key, entity and starts it.
const deletionStart = vi.fn();
const useDeferredActionInput = vi.fn();
let deletionCountdown: React.ReactNode = null;
let deletionIsPending = false;
vi.mock('@/hooks/useDeferredAction', () => ({
  useDeferredAction: (input: unknown) => {
    useDeferredActionInput(input);
    return {
      pending: null,
      isPending: deletionIsPending,
      isBlocked: false,
      start: deletionStart,
      cancel: vi.fn(),
      countdown: deletionCountdown,
    };
  },
}));

import { SPODocumentDetail } from './SPODocumentDetail';
import type { SPODocument, SPODocumentLine } from '../types/spoDocument.types';

function line(over: Partial<SPODocumentLine> = {}): SPODocumentLine {
  return {
    id: 'line-1',
    spo_number: 'SPO-2026/08-0061',
    product_id: 'prod-1',
    product: { id: 'prod-1', product_code: 'CW-BASIN-450', product_name: 'Ceramic Wash Basin 450mm' },
    warehouse_id: 'wh-1',
    warehouse: { id: 'wh-1', warehouse_code: 'BRW-IB', warehouse_name: 'Brickworks Ipoh' },
    allocated_quantity: 300,
    quantity_received: 100,
    quantity_rejected: 0,
    balance: 200,
    arrival_date: '2026-08-15',
    overdue_days: 0,
    supplier_name: 'Acme Sanitary',
    supplier_id: 'sup-1',
    expected_date: '2026-08-15',
    planning_span: 'in_plan',
    receipt_status: 'open',
    outstanding: true,
    inbound_shipment: null,
    ...over,
  };
}

function doc(over: Partial<SPODocument> = {}): SPODocument {
  return {
    spo_number: 'SPO-2026/08-0061',
    doc_date: '2026-08-01',
    supplier_name: 'Acme Sanitary',
    supplier_extra_count: 0,
    linked_grns: [],
    status: 'outstanding',
    total_allocated: 300,
    total_received: 100,
    balance: 200,
    line_count: 1,
    lines: [line()],
    ...over,
  };
}

function renderDetail(spoNumber = 'SPO-2026/08-0061') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SPODocumentDetail spoNumber={spoNumber} />
    </QueryClientProvider>,
  );
}

function openTab(name: 'Header' | 'Lines') {
  fireEvent.mouseDown(screen.getByRole('tab', { name }), { button: 0, ctrlKey: false });
}

/** Radix opens the gear on pointerdown, not click. */
function openGear() {
  const trigger = screen.getByRole('button', { name: 'SPO document options' });
  fireEvent.pointerDown(trigger, new MouseEvent('pointerdown', { bubbles: true, button: 0 }));
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  searchParams = new URLSearchParams();
  updateMutateAsync.mockResolvedValue(undefined);
  deleteMutateAsync.mockResolvedValue(undefined);
  deletionCountdown = null;
  deletionIsPending = false;
});

describe('SPODocumentDetail - status pill (AC-2, AC-6)', () => {
  it('words the header status Outstanding in green', () => {
    useSPODocument.mockReturnValue({ data: doc(), isLoading: false, isError: false });
    renderDetail();

    const pill = screen.getByText('Outstanding');
    expect(pill.className).toMatch(/green/);
  });

  it('words a fully-received document Completed', () => {
    useSPODocument.mockReturnValue({
      data: doc({ status: 'completed' }),
      isLoading: false,
      isError: false,
    });
    renderDetail();

    expect(screen.getByText('Completed')).toBeInTheDocument();
    expect(screen.queryByText('Outstanding')).toBeNull();
  });
});

describe('SPODocumentDetail - Plan badge, all four states (Q4, AC-6)', () => {
  it('renders In plan / Pool / Off / No location across the document lines', () => {
    useSPODocument.mockReturnValue({
      data: doc({
        line_count: 4,
        lines: [
          line({ id: 'l-in-plan', planning_span: 'in_plan' }),
          line({ id: 'l-pool', planning_span: 'pool' }),
          line({ id: 'l-off', planning_span: 'off' }),
          line({
            id: 'l-none',
            planning_span: 'none',
            warehouse_id: null,
            warehouse: null,
          }),
        ],
      }),
      isLoading: false,
      isError: false,
    });
    renderDetail();
    openTab('Lines');

    // The warehouse column ALSO reads "No location" for the unlocated line (a
    // different span, no `warehouse`) - scope the badge assertion to Badge
    // itself (`data-slot="badge"`) so it isn't confused with that column.
    const badgeLabels = Array.from(
      document.querySelectorAll('[data-slot="badge"]'),
    ).map((el) => el.textContent);
    expect(badgeLabels).toEqual(
      expect.arrayContaining(['In plan', 'Pool', 'Off', 'No location']),
    );
  });
});

describe('SPODocumentDetail - highlight on URL filter (AC-7)', () => {
  it('highlights the matching line while every line on the document stays visible', () => {
    searchParams = new URLSearchParams('product_id=prod-1');
    useSPODocument.mockReturnValue({
      data: doc({
        line_count: 2,
        lines: [
          line({ id: 'l-match', product_id: 'prod-1', product: { id: 'prod-1', product_code: 'CW-BASIN-450', product_name: 'Basin' } }),
          line({ id: 'l-no-match', product_id: 'prod-2', product: { id: 'prod-2', product_code: 'CW-TAP-200', product_name: 'Tap' } }),
        ],
      }),
      isLoading: false,
      isError: false,
    });
    renderDetail();
    openTab('Lines');

    // Both lines still render - filters narrow the LIST, not the lines tab (Q10).
    expect(screen.getByText('CW-BASIN-450')).toBeInTheDocument();
    expect(screen.getByText('CW-TAP-200')).toBeInTheDocument();

    // Exactly one line is marked as matching.
    expect(screen.getAllByTitle('Matches your filter')).toHaveLength(1);
    const matchedRow = screen.getByText('CW-BASIN-450').closest('tr') as HTMLElement;
    expect(within(matchedRow).getByTitle('Matches your filter')).toBeInTheDocument();
    const unmatchedRow = screen.getByText('CW-TAP-200').closest('tr') as HTMLElement;
    expect(within(unmatchedRow).queryByTitle('Matches your filter')).toBeNull();

    // The banner names how many lines matched.
    expect(
      screen.getByText(/1 line below match your product\/warehouse filter/i),
    ).toBeInTheDocument();
  });

  it('highlights nothing and shows no banner when the URL carries no product/warehouse filter', () => {
    searchParams = new URLSearchParams();
    useSPODocument.mockReturnValue({
      data: doc({
        line_count: 2,
        lines: [
          line({ id: 'l-a', product_id: 'prod-1' }),
          line({ id: 'l-b', product_id: 'prod-2' }),
        ],
      }),
      isLoading: false,
      isError: false,
    });
    renderDetail();
    openTab('Lines');

    expect(screen.queryByTitle('Matches your filter')).toBeNull();
    expect(screen.queryByText(/match your product\/warehouse filter/i)).toBeNull();
  });

  it('matches on warehouse_id too, composing with product_id', () => {
    searchParams = new URLSearchParams('product_id=prod-1&warehouse_id=wh-1');
    useSPODocument.mockReturnValue({
      data: doc({
        line_count: 2,
        lines: [
          // Same product, but a DIFFERENT warehouse - must not match.
          line({
            id: 'l-wrong-wh',
            product_id: 'prod-1',
            warehouse_id: 'wh-2',
            warehouse: { id: 'wh-2', warehouse_code: 'HQ', warehouse_name: 'HQ' },
            product: { id: 'prod-1', product_code: 'CW-BASIN-450', product_name: 'Basin' },
          }),
          // Same product AND same warehouse - matches.
          line({
            id: 'l-right-wh',
            product_id: 'prod-1',
            warehouse_id: 'wh-1',
            warehouse: { id: 'wh-1', warehouse_code: 'BRW-IB', warehouse_name: 'Brickworks Ipoh' },
            product: { id: 'prod-1', product_code: 'CW-BASIN-450', product_name: 'Basin' },
          }),
        ],
      }),
      isLoading: false,
      isError: false,
    });
    renderDetail();
    openTab('Lines');

    expect(screen.getAllByTitle('Matches your filter')).toHaveLength(1);
  });
});

describe('SPODocumentDetail - Edit/Save calls the real mutations (review B2)', () => {
  it('Save PUTs only the line whose draft changed, with every editable field (UAT AC-24)', async () => {
    useSPODocument.mockReturnValue({ data: doc(), isLoading: false, isError: false });
    renderDetail();

    fireEvent.click(screen.getByRole('button', { name: /^Edit$/i }));
    openTab('Lines');

    const allocatedInput = screen.getByLabelText('Allocated qty on CW-BASIN-450');
    fireEvent.change(allocatedInput, { target: { value: '350' } });

    await fireEvent.click(screen.getByRole('button', { name: /^Save$/i }));

    expect(updateMutateAsync).toHaveBeenCalledWith({
      id: 'line-1',
      data: {
        product_id: 'prod-1',
        warehouse_id: 'wh-1',
        allocated_quantity: 350,
        quantity_received: 100,
        quantity_rejected: 0,
        expected_date: '2026-08-15',
        supplier_id: 'sup-1',
      },
    });
    expect(deleteMutateAsync).not.toHaveBeenCalled();
  });

  it('Save carries a changed ETA through to the update payload (UAT AC-24 part 2)', async () => {
    useSPODocument.mockReturnValue({ data: doc(), isLoading: false, isError: false });
    renderDetail();

    fireEvent.click(screen.getByRole('button', { name: /^Edit$/i }));
    openTab('Lines');

    const etaInput = screen.getByLabelText('ETA on CW-BASIN-450');
    fireEvent.change(etaInput, { target: { value: '2026-09-01' } });

    await fireEvent.click(screen.getByRole('button', { name: /^Save$/i }));

    expect(updateMutateAsync).toHaveBeenCalledWith({
      id: 'line-1',
      data: expect.objectContaining({ expected_date: '2026-09-01' }),
    });
  });

  it('Save leaves an untouched line alone and DELETEs a removed one', async () => {
    useSPODocument.mockReturnValue({
      data: doc({
        line_count: 2,
        lines: [
          line({ id: 'l-keep', product: { id: 'prod-1', product_code: 'CW-BASIN-450', product_name: 'Basin' } }),
          line({ id: 'l-remove', product_id: 'prod-2', product: { id: 'prod-2', product_code: 'CW-TAP-200', product_name: 'Tap' } }),
        ],
      }),
      isLoading: false,
      isError: false,
    });
    renderDetail();

    fireEvent.click(screen.getByRole('button', { name: /^Edit$/i }));
    openTab('Lines');

    fireEvent.click(screen.getAllByRole('button', { name: /^Remove$/i })[1]);
    await fireEvent.click(screen.getByRole('button', { name: /^Save$/i }));

    expect(updateMutateAsync).not.toHaveBeenCalled();
    expect(deleteMutateAsync).toHaveBeenCalledWith('l-remove');
  });

  it('no draft changes and nothing removed saves nothing and says so', async () => {
    useSPODocument.mockReturnValue({ data: doc(), isLoading: false, isError: false });
    renderDetail();

    fireEvent.click(screen.getByRole('button', { name: /^Edit$/i }));
    await fireEvent.click(screen.getByRole('button', { name: /^Save$/i }));

    expect(updateMutateAsync).not.toHaveBeenCalled();
    expect(deleteMutateAsync).not.toHaveBeenCalled();
  });
});

describe('SPODocumentDetail - Back moved to the page header (UAT AC-21)', () => {
  it('no longer renders its own Back link - the page-level PageHeader owns it', () => {
    useSPODocument.mockReturnValue({ data: doc(), isLoading: false, isError: false });
    renderDetail();

    expect(screen.queryByText(/Back to SPO Allocations/i)).toBeNull();
  });
});

describe('SPODocumentDetail - the active tab lives in the URL (UAT AC-22)', () => {
  it('opening the Lines tab writes ?tab=lines, so the pager carries it forward', () => {
    useSPODocument.mockReturnValue({ data: doc(), isLoading: false, isError: false });
    renderDetail();

    openTab('Lines');

    expect(routerReplace).toHaveBeenCalledWith(
      expect.stringContaining('tab=lines'),
      expect.objectContaining({ scroll: false }),
    );
  });

  it('starts on the Lines tab when the url already carries ?tab=lines', () => {
    searchParams = new URLSearchParams('tab=lines');
    useSPODocument.mockReturnValue({ data: doc(), isLoading: false, isError: false });
    renderDetail();

    expect(screen.getByRole('tab', { name: 'Lines' })).toHaveAttribute('data-state', 'active');
    expect(screen.getByRole('tab', { name: 'Header' })).toHaveAttribute('data-state', 'inactive');
  });

  it('switching back to Header drops the tab param from the url', () => {
    searchParams = new URLSearchParams('tab=lines');
    useSPODocument.mockReturnValue({ data: doc(), isLoading: false, isError: false });
    renderDetail();

    openTab('Header');

    const [href] = routerReplace.mock.calls[0];
    expect(href as string).not.toContain('tab=');
  });
});

describe('SPODocumentDetail - Lines Columns control, Rejected/Overdue hidden by default (UAT AC-23)', () => {
  it('offers a Columns control on the Lines tab', () => {
    useSPODocument.mockReturnValue({ data: doc(), isLoading: false, isError: false });
    renderDetail();
    openTab('Lines');

    expect(screen.getByRole('button', { name: /columns/i })).toBeInTheDocument();
  });

  it('does not render the Rejected or Overdue columns until toggled on', () => {
    useSPODocument.mockReturnValue({ data: doc(), isLoading: false, isError: false });
    renderDetail();
    openTab('Lines');

    expect(screen.queryByText('Rejected')).toBeNull();
    expect(screen.queryByText('Overdue')).toBeNull();
    // Every other Lines column stays visible.
    expect(screen.getByText('Balance')).toBeInTheDocument();
  });
});

describe('SPODocumentDetail - gear Delete document (UAT AC-26)', () => {
  it('parks the spo_document.delete pending action for this spo_number', () => {
    useSPODocument.mockReturnValue({ data: doc(), isLoading: false, isError: false });
    renderDetail();

    openGear();
    fireEvent.click(screen.getByRole('menuitem', { name: 'Delete document' }));

    expect(deletionStart).toHaveBeenCalledTimes(1);
    const input = useDeferredActionInput.mock.calls[0][0] as {
      actionKey: string;
      entityType: string;
      entityId: string;
    };
    expect(input.actionKey).toBe('spo_document.delete');
    expect(input.entityType).toBe('spo_document');
    expect(input.entityId).toBe('SPO-2026/08-0061');
  });

  it('cancel never deletes anything - only start() does', () => {
    useSPODocument.mockReturnValue({ data: doc(), isLoading: false, isError: false });
    renderDetail();

    openGear();
    // Closing the menu without selecting the item.
    fireEvent.keyDown(document.activeElement || document.body, { key: 'Escape' });

    expect(deletionStart).not.toHaveBeenCalled();
  });

  it('shows the countdown in place of Edit while the deletion is pending', () => {
    deletionCountdown = <button type="button">Deleting in 8s</button>;
    useSPODocument.mockReturnValue({ data: doc(), isLoading: false, isError: false });
    renderDetail();

    expect(screen.getByText('Deleting in 8s')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Edit$/i })).toBeNull();
  });
});
