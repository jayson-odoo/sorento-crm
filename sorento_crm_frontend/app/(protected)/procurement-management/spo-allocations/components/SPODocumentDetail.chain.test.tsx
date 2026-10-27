/**
 * LINKAGE-UNIFY U4 (PLAN section 12, item 3, F4): the SPO document's "SO covered" lists a
 * placement that reached this SPO through its PO line, marked "via PO <number>".
 * Harness copied from `SPODocumentDetail.test.tsx`; `via_po` is not on the app's type yet.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, within, fireEvent, waitFor } from '@testing-library/react';
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

// `dismiss` is here even though `useDeferredAction` is mocked below: the
// pending-entity store this hook would otherwise drive calls `toast.dismiss`
// on its own follow-through timer, and a mock missing the key throws if
// anything in this file ever exercises the real hook.
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), dismiss: vi.fn() } }));

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
    grns: [],
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

function coveredDoc() {
  return doc({
    lines: [
      line({
        so_covered: [
          { document: 'SO396500', customer: 'Acme', demand_class: 'project', qty: 60 },
          { document: 'SO396349', customer: 'Beta', demand_class: 'project', qty: 294,
            via_po: '202607-S0100' },
        ] as never,
      }),
    ],
  });
}

describe('F4 SPODocumentDetail SO covered', () => {
  it('seed: the SO covered chip counts both placements', () => {
    useSPODocument.mockReturnValue({ data: coveredDoc(), isLoading: false, isError: false });
    renderDetail();
    openTab('Lines');
    expect(screen.getByText('2 SOs · 354')).toBeInTheDocument();
  });

  it('the lightbox marks the via-PO row "via PO 202607-S0100" and no other row', () => {
    useSPODocument.mockReturnValue({ data: coveredDoc(), isLoading: false, isError: false });
    renderDetail();
    openTab('Lines');
    fireEvent.click(screen.getByText('2 SOs · 354'));
    expect(screen.getByText('SO396349')).toBeInTheDocument();
    expect(screen.getByText('via PO 202607-S0100')).toBeInTheDocument();
    expect(screen.getAllByText(/via PO/)).toHaveLength(1);
  });
});
