/**
 * SEARCH-CHIPS slice 2 (UAC S1, S2, S4 as for Sales orders): the Proforma invoices list's
 * search box in chips mode. Plan `documentation/plans/ui/PLAN-search-chips-b-12nov.md`.
 *
 * The REAL `useProformaInvoices` -> `listProformaInvoices` chain runs and only `apiFetch` is
 * stubbed, so the assertions read the actual GET /api/v1/scm/proforma-invoices the browser
 * would send.
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
  });
}
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver =
  ResizeObserverStub;
Element.prototype.scrollIntoView = vi.fn();

const nav = vi.hoisted(() => ({ search: '', replace: vi.fn() }));
vi.mock('@/lib/toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
    custom: vi.fn(),
  },
}));
vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/proforma-invoices',
  useRouter: () => ({ push: vi.fn(), replace: nav.replace }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({
    resetToDefaults: vi.fn(),
    isLoading: false,
  }),
}));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('../../hooks/useFulfilment', () => ({
  useFulfilmentSuppliers: () => ({
    data: [{ value: 'sup-1', label: 'ZZT Supplier One' }],
  }),
  useContainerSizes: () => ({ data: [], isLoading: false }),
}));
vi.mock('./SupplierDocumentsUploadDialog', () => ({
  SupplierDocumentsUploadDialog: () => null,
}));
vi.mock('./ConvertToPackingListDialog', () => ({
  ConvertToPackingListDialog: () => null,
}));
// The real list hook (and through it the real service); the mutations stubbed.
vi.mock('../../hooks/useProformaInvoices', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../../hooks/useProformaInvoices')>();
  return {
    ...actual,
    useConvertProformaInvoicesToDraftShipment: () => ({
      mutateAsync: vi.fn(),
      isPending: false,
    }),
    useBulkDeleteProformaInvoices: () => ({
      mutateAsync: vi.fn(),
      isPending: false,
    }),
    useProformaInvoicesApplied: () => vi.fn(),
  };
});

const api = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  apiFetch: (...a: unknown[]) => api.apiFetch(...a),
}));

import { ProformaInvoicesView } from './ProformaInvoicesView';

const SEARCH_LABEL = 'Search proforma invoices';

const ROW = {
  id: 'pi-1',
  supplier_id: 'sup-1',
  supplier_code: 'ZZT1',
  supplier_name: 'ZZT Supplier One',
  pi_number: 'ZZT-PI-001',
  supplier_ref: 'ZZT-REF',
  invoice_date: '2026-08-01',
  currency: 'CNY',
  container_no: 'TEMU1',
  seal_no: 'S1',
  consignee: 'ZZT CONSIGNEE',
  bl_no: 'BL1',
  total_amount: 1000,
  line_count: 5,
  source_ref: null,
  block_index: 0,
  uploaded_by: 'ZZT',
  created_at: '2026-08-01T02:00:00',
  updated_at: '2026-08-01T02:00:00',
  total_cbm: 1,
  unmeasured_lines: 0,
  status: 'current',
  revision_no: 1,
  revision_count: 1,
  adjusted_by: null,
  adjusted_at: null,
  is_adjusted: false,
  placement: 'not_converted',
  placed_qty: 0,
  total_qty: 500,
  remaining_qty: 500,
  packing_lists: [],
};

function answerList() {
  api.apiFetch.mockImplementation(async () => ({
    ok: true,
    status: 200,
    json: async () => ({ data: [ROW], total: 80, limit: 25, offset: 0 }),
    text: async () =>
      JSON.stringify({ data: [ROW], total: 80, limit: 25, offset: 0 }),
  }));
}

/** Every list GET the page sent, as parsed search params. */
function listRequests(): URLSearchParams[] {
  return api.apiFetch.mock.calls
    .map((c) => String(c[0]))
    .filter((u) => u.includes('/api/v1/scm/proforma-invoices?'))
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
    (u) => new URL(u, 'http://localhost/scm/proforma-invoices'),
  );
}

function renderList() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ProformaInvoicesView />
    </QueryClientProvider>,
  );
}

function searchBox() {
  return screen.getByRole('textbox', { name: SEARCH_LABEL });
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

describe('ProformaInvoicesView search chips', () => {
  it('two chips plus the typed text reach GET /scm/proforma-invoices as one query param each', async () => {
    const user = userEvent.setup();
    renderList();
    expect(await screen.findByText('ZZT-PI-001')).toBeInTheDocument();

    await user.type(searchBox(), 'PI2611001{Enter}');
    await user.type(searchBox(), 'Acme Trading{Enter}');
    expect(
      screen.getByRole('button', { name: 'Remove PI2611001' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Remove Acme Trading' }),
    ).toBeInTheDocument();
    await user.type(searchBox(), 'Fakeco');

    await waitFor(() => {
      const queries = lastListRequest().getAll('query');
      expect(queries).toHaveLength(3);
      expect(queries).toEqual(
        expect.arrayContaining(['PI2611001', 'Acme Trading', 'Fakeco']),
      );
    });
  });

  it('a list URL with two query params restores two chips and searches both', async () => {
    nav.search = 'page=1&limit=25&query=PI2611001&query=Acme%2C+Trading';
    renderList();

    expect(
      await screen.findByRole('button', { name: 'Remove PI2611001' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Remove Acme, Trading' }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(lastListRequest().getAll('query')).toEqual([
        'PI2611001',
        'Acme, Trading',
      ]);
    });
    expect(searchBox()).toHaveValue('');
  });

  it('adding chips writes them into the address bar', async () => {
    const user = userEvent.setup();
    renderList();
    await screen.findByText('ZZT-PI-001');

    await user.type(searchBox(), 'PI1{Enter}PI2{Enter}');
    await waitFor(() => {
      const written = writtenUrls().filter(
        (u) => u.searchParams.getAll('query').length === 2,
      );
      expect(written.length).toBeGreaterThan(0);
      const last = written.at(-1)!;
      expect(last.searchParams.getAll('query')).toEqual(['PI1', 'PI2']);
      expect(last.pathname).toBe('/scm/proforma-invoices');
    });
  });
});
