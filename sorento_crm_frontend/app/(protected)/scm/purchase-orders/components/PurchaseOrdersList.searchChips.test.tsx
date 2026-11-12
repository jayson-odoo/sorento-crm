/**
 * SEARCH-CHIPS slice 2 (UAC S1, S2, S4 as for Sales orders): the Purchase orders list's
 * search box in chips mode. Plan `documentation/plans/ui/PLAN-search-chips-b-12nov.md`.
 *
 * The REAL `usePurchaseOrders` -> `getPurchaseOrders` -> `buildDataGridParams` chain runs and
 * only `apiFetch` is stubbed, so the assertions read the actual list GET the browser would send.
 * - chips + typed text reach GET /api/v1/scm/purchase-orders as one `query` param each;
 * - a list URL carrying two `query` params (Back from a record) restores two chips;
 * - adding a chip writes the list's state into the address bar.
 * Red first: the list passes no chips to `ListSearchInput` and sends one `query`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

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
Element.prototype.scrollIntoView = vi.fn();

const nav = vi.hoisted(() => ({ search: '', replace: vi.fn() }));
vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/purchase-orders',
  useRouter: () => ({ push: vi.fn(), replace: nav.replace }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({
    resetToDefaults: async () => {},
    isLoading: false,
  }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
type MenuProps = {
  children?: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
};
vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: MenuProps) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: MenuProps) => <>{children}</>,
  DropdownMenuContent: ({ children }: MenuProps) => <div>{children}</div>,
  DropdownMenuItem: ({ children, onClick, disabled }: MenuProps) => (
    <button type="button" onClick={onClick} disabled={disabled}>
      {children}
    </button>
  ),
  DropdownMenuCheckboxItem: ({ children }: MenuProps) => <div>{children}</div>,
  DropdownMenuLabel: ({ children }: MenuProps) => <div>{children}</div>,
  DropdownMenuSeparator: () => <hr />,
  DropdownMenuGroup: ({ children }: MenuProps) => <div>{children}</div>,
  DropdownMenuPortal: ({ children }: MenuProps) => <>{children}</>,
  DropdownMenuSub: ({ children }: MenuProps) => <div>{children}</div>,
  DropdownMenuSubContent: ({ children }: MenuProps) => <div>{children}</div>,
  DropdownMenuSubTrigger: ({ children }: MenuProps) => <div>{children}</div>,
}));
vi.mock('../../hooks/usePurchaseOrderActions', () => ({
  usePurchaseOrderActions: () => ({
    confirm: { mutateAsync: vi.fn(), isPending: false },
    createGr: { mutateAsync: vi.fn(), isPending: false },
    bulkDelete: { mutateAsync: vi.fn(), isPending: false },
  }),
}));
vi.mock('../../reorder/components/OutstandingUploadDialog', () => ({
  OutstandingUploadDialog: () => null,
}));

const api = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  apiFetch: (...a: unknown[]) => api.apiFetch(...a),
}));

import PurchaseOrdersList from './PurchaseOrdersList';

const PLACEHOLDER = 'Search PO or supplier...';

const ROW = {
  id: 'po-1',
  po_number: 'ZZT-PO-0001',
  supplier_code: 'SUP-ACME',
  supplier_name: 'Fakeco Sanitary',
  warehouse_code: 'WH-KL',
  warehouse_name: 'Test DC',
  status: 'active',
  order_date: '2026-07-16',
  expected_date: null,
  total_qty: 320,
  line_count: 1,
  lines: [],
  created_at: '2026-07-16T00:00:00',
};

function answerList() {
  api.apiFetch.mockImplementation(async () => ({
    ok: true,
    status: 200,
    json: async () => ({
      data: [ROW],
      pagination: { total: 80, page: 1 },
      empty: false,
      product_cost: null,
    }),
    text: async () => '',
  }));
}

/** Every list GET the page sent, as parsed search params. */
function listRequests(): URLSearchParams[] {
  return api.apiFetch.mock.calls
    .map((c) => String(c[0]))
    .filter((u) => u.includes('/api/v1/scm/purchase-orders?'))
    .map((u) => new URLSearchParams(u.slice(u.indexOf('?') + 1)));
}

function lastListRequest(): URLSearchParams {
  const all = listRequests();
  expect(all.length).toBeGreaterThan(0);
  return all.at(-1)!;
}

/** Every URL the list wrote into the address bar, however it wrote it. */
function writtenUrls(): URL[] {
  const viaHistory = (replaceState.mock.calls as unknown[][]).map((c) =>
    String(c[2] ?? ''),
  );
  const viaRouter = nav.replace.mock.calls.map((c) => String(c[0] ?? ''));
  return [...viaHistory, ...viaRouter].map(
    (u) => new URL(u, 'http://localhost/scm/purchase-orders'),
  );
}

function renderList() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <PurchaseOrdersList />
    </QueryClientProvider>,
  );
}

function searchBox() {
  return screen.getByRole('textbox', { name: PLACEHOLDER });
}

let replaceState: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  nav.search = '';
  answerList();
  replaceState = vi.spyOn(window.history, 'replaceState');
});

afterEach(() => {
  replaceState.mockRestore();
});

describe('PurchaseOrdersList search chips', () => {
  it('two chips plus the typed text reach GET /scm/purchase-orders as one query param each', async () => {
    const user = userEvent.setup();
    renderList();
    expect(await screen.findByText('ZZT-PO-0001')).toBeInTheDocument();

    await user.type(searchBox(), 'PO4500123{Enter}');
    await user.type(searchBox(), 'Acme Trading{Enter}');
    expect(
      screen.getByRole('button', { name: 'Remove PO4500123' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Remove Acme Trading' }),
    ).toBeInTheDocument();
    await user.type(searchBox(), 'Fakeco');

    await waitFor(() => {
      const queries = lastListRequest().getAll('query');
      expect(queries).toHaveLength(3);
      expect(queries).toEqual(
        expect.arrayContaining(['PO4500123', 'Acme Trading', 'Fakeco']),
      );
    });
  });

  it('a list URL with two query params restores two chips and searches both', async () => {
    nav.search = 'page=1&limit=25&query=PO4500123&query=Acme%2C+Trading';
    renderList();

    expect(
      await screen.findByRole('button', { name: 'Remove PO4500123' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Remove Acme, Trading' }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(lastListRequest().getAll('query')).toEqual([
        'PO4500123',
        'Acme, Trading',
      ]);
    });
    expect(searchBox()).toHaveValue('');
  });

  it('adding chips writes them into the address bar', async () => {
    const user = userEvent.setup();
    renderList();
    await screen.findByText('ZZT-PO-0001');

    await user.type(searchBox(), 'PO1{Enter}PO2{Enter}');
    await waitFor(() => {
      const written = writtenUrls().filter(
        (u) => u.searchParams.getAll('query').length === 2,
      );
      expect(written.length).toBeGreaterThan(0);
      const last = written.at(-1)!;
      expect(last.searchParams.getAll('query')).toEqual(['PO1', 'PO2']);
      expect(last.pathname).toBe('/scm/purchase-orders');
    });
  });
});

describe('PurchaseOrdersList search chips: the Order Inquiries upload hand-off', () => {
  // `?documents=a,b` is how the Order Inquiries page sends the buyer to the orders one upload
  // wrote (OrderInquiriesClient.tsx `purchaseOrdersHref`). A search must not drop it from the
  // address bar, or a reload / shared link shows the whole book.
  it('adding chips keeps documents in the address bar beside the query params', async () => {
    nav.search = 'documents=ZZT-PO-0001%2CZZT-PO-0002';
    const user = userEvent.setup();
    renderList();
    await screen.findByText('ZZT-PO-0001');
    // Guard: the list itself is narrowed to those documents.
    await waitFor(() =>
      expect(lastListRequest().get('documents')).toBe(
        'ZZT-PO-0001,ZZT-PO-0002',
      ),
    );

    await user.type(searchBox(), 'PO1{Enter}PO2{Enter}');
    await waitFor(() => {
      const written = writtenUrls().filter(
        (u) => u.searchParams.getAll('query').length === 2,
      );
      expect(written.length).toBeGreaterThan(0);
      const last = written.at(-1)!;
      expect(last.searchParams.getAll('query')).toEqual(['PO1', 'PO2']);
      const docs = last.searchParams
        .getAll('documents')
        .flatMap((d) => d.split(','));
      expect(docs.sort()).toEqual(['ZZT-PO-0001', 'ZZT-PO-0002']);
    });
  });
});
