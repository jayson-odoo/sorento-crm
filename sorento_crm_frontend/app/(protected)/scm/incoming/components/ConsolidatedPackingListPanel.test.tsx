/**
 * S10 - the container as one list.
 *
 * What is asserted is what Ms Tee would be misled by: a factory shown without its subtotal, a
 * split that prints one company and leaves the other to be inferred, a line that differs from
 * the loading plan without saying so, and a planned line that never arrived being silently
 * absent rather than named.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// jsdom polyfills required by ScrollArea / DataGrid.
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

vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/incoming',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

// DataGrid persists column prefs via this hook (fires network) - stub it.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const toastError = vi.fn();
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: (...a: unknown[]) => toastError(...a), info: vi.fn(), warning: vi.fn() },
}));

const state = {
  getList: vi.fn(),
  download: vi.fn(),
};

vi.mock('../../services/fulfilmentService', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../services/fulfilmentService')>()),
  getConsolidatedPackingList: (...a: unknown[]) => state.getList(...a),
  downloadPackingListExport: (...a: unknown[]) => state.download(...a),
}));

import { ConsolidatedPackingListPanel } from './ConsolidatedPackingListPanel';
import type { ConsolidatedPackingList } from '../../services/fulfilmentService';

const KAILU_LINE = {
  line_id: 'l-1',
  product_id: 'p-1',
  product_code: 'SRTWT7443',
  product_name: 'Basin Mixer Tall',
  brand: 'SORENTO',
  company: 'SORENTO' as const,
  qty: 490,
  cartons: 86,
  cbm: 2.10528,
  remarks: 'Packed on two pallets',
  discrepancies: ['Loading plan asked 500, packed 490 (short 10)'],
};

const MOCHA_LINE = {
  line_id: 'l-2',
  product_id: 'p-2',
  product_code: 'MCHWT1200',
  product_name: 'Shower Set',
  brand: 'MOCHA',
  company: 'MOCHA' as const,
  qty: 900,
  cartons: 55,
  cbm: 7.307,
  remarks: null,
  discrepancies: [],
};

const CAIZHOU_LINE = {
  line_id: 'l-3',
  product_id: 'p-3',
  product_code: 'SRTBT2200',
  product_name: 'Bath Tub 1700',
  brand: 'SANDEL',
  company: 'SORENTO' as const,
  qty: 120,
  cartons: 30,
  cbm: null,
  remarks: null,
  discrepancies: ['Not on the loading plan'],
};

function packingList(over: Partial<ConsolidatedPackingList> = {}): ConsolidatedPackingList {
  return {
    shipment_id: 'sh-1',
    shipment_number: 'FSCU8103365',
    container_no: 'FSCU8103365',
    bl_no: null,
    status: 'in_transit',
    factories: [
      {
        supplier_id: 'sup-a',
        supplier_code: '400-K029',
        supplier_name: 'KAILU HARDWARE FACTORY',
        loading_plan_id: 'lp-1',
        notice_id: 'n-1',
        lines: [KAILU_LINE, MOCHA_LINE],
        not_packed: [
          {
            product_id: 'p-9',
            product_code: 'SRTWT7301-BL',
            product_name: 'Kitchen Sink',
            planned_qty: 100,
          },
        ],
        subtotal: { lines: 2, qty: 1390, cartons: 141, cbm: 9.4123 },
      },
      {
        supplier_id: 'sup-b',
        supplier_code: '400-C011',
        supplier_name: 'CAIZHOU SANITARY',
        loading_plan_id: null,
        notice_id: null,
        lines: [CAIZHOU_LINE],
        not_packed: [],
        subtotal: { lines: 1, qty: 120, cartons: 30, cbm: 0 },
      },
    ],
    total: { lines: 3, qty: 1510, cartons: 171, cbm: 9.4123 },
    split: [
      { company: 'SORENTO', lines: 2, qty: 610, cartons: 116, cbm: 2.10528 },
      { company: 'MOCHA', lines: 1, qty: 900, cartons: 55, cbm: 7.307 },
    ],
    ...over,
  };
}

function emptyList(): ConsolidatedPackingList {
  return packingList({
    factories: [],
    total: { lines: 0, qty: 0, cartons: 0, cbm: 0 },
    split: [
      { company: 'SORENTO', lines: 0, qty: 0, cartons: 0, cbm: 0 },
      { company: 'MOCHA', lines: 0, qty: 0, cartons: 0, cbm: 0 },
    ],
  });
}

function renderPanel(shipmentId: string | null = 'sh-1') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ConsolidatedPackingListPanel shipmentId={shipmentId} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  state.getList = vi.fn().mockResolvedValue(packingList());
  state.download = vi.fn().mockResolvedValue(undefined);
});

describe('ConsolidatedPackingListPanel', () => {
  it('shows a skeleton while the list is still being read', () => {
    state.getList = vi.fn(() => new Promise(() => {}));
    renderPanel();

    expect(screen.getByTestId('packing-list-loading')).toBeInTheDocument();
  });

  it('says why the list is missing rather than showing an empty card', async () => {
    state.getList = vi.fn().mockRejectedValue(new Error('Packing list is unavailable'));
    renderPanel();

    expect(await screen.findByText('Packing list is unavailable')).toBeInTheDocument();
  });

  it('states plainly that a container has nothing on it yet', async () => {
    state.getList = vi.fn().mockResolvedValue(emptyList());
    renderPanel();

    expect(await screen.findByText('No lines on this container yet.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /download/i })).toBeDisabled();
  });

  it('renders nothing until a container is chosen', () => {
    renderPanel(null);

    expect(screen.queryByText('Sorento packing list')).not.toBeInTheDocument();
    expect(state.getList).not.toHaveBeenCalled();
  });

  it('groups the container by factory, each with its own subtotal', async () => {
    renderPanel();

    expect(await screen.findByText('KAILU HARDWARE FACTORY')).toBeInTheDocument();
    expect(screen.getByText('CAIZHOU SANITARY')).toBeInTheDocument();

    // Kailu's subtotal, then Caizhou's - the figures that make each section stand alone.
    expect(screen.getByText('1,390 qty')).toBeInTheDocument();
    expect(screen.getByText('141 ctn')).toBeInTheDocument();
    expect(screen.getByText('9.4123 cbm')).toBeInTheDocument();
    expect(screen.getByText('120 qty')).toBeInTheDocument();
    expect(screen.getByText('30 ctn')).toBeInTheDocument();
  });

  it('lists every line under the factory that loaded it', async () => {
    renderPanel();

    expect(await screen.findByText('SRTWT7443')).toBeInTheDocument();
    expect(screen.getByText('MCHWT1200')).toBeInTheDocument();
    expect(screen.getByText('SRTBT2200')).toBeInTheDocument();
    expect(screen.getByText('Basin Mixer Tall')).toBeInTheDocument();
  });

  it("keeps the supplier's own remark and our derived difference apart", async () => {
    renderPanel();

    expect(await screen.findByText('Packed on two pallets')).toBeInTheDocument();
    const discrepancy = screen.getByText('Loading plan asked 500, packed 490 (short 10)');
    expect(discrepancy.className).toContain('text-amber-600');
    expect(screen.getByText('Not on the loading plan').className).toContain('text-amber-600');
  });

  it('names a planned line the factory never packed', async () => {
    renderPanel();

    const item = await screen.findByRole('listitem');
    expect(item).toHaveTextContent('SRTWT7301-BL - not packed - loading plan asked 100');
  });

  it('prints the grand total and both company rows of the split', async () => {
    renderPanel();

    const footer = within(await screen.findByTestId('packing-list-footer'));
    expect(footer.getByText('Total')).toBeInTheDocument();
    expect(footer.getByText('1,510 qty · 171 ctn · 9.4123 cbm')).toBeInTheDocument();
    expect(footer.getByText('SORENTO')).toBeInTheDocument();
    expect(footer.getByText('610 qty · 116 ctn · 2.1053 cbm')).toBeInTheDocument();
    expect(footer.getByText('MOCHA')).toBeInTheDocument();
    expect(footer.getByText('900 qty · 55 ctn · 7.3070 cbm')).toBeInTheDocument();
  });

  it('prints a company row the payload left out, as zeros rather than as nothing', async () => {
    // An absent row reads as the whole container belonging to the other company.
    state.getList = vi.fn().mockResolvedValue(
      packingList({ split: [{ company: 'SORENTO', lines: 3, qty: 1510, cartons: 171, cbm: 9.4123 }] }),
    );
    renderPanel();

    const footer = within(await screen.findByTestId('packing-list-footer'));
    expect(footer.getByText('MOCHA')).toBeInTheDocument();
    expect(footer.getByText('0 qty · 0 ctn · 0.0000 cbm')).toBeInTheDocument();
  });

  it('downloads the workbook for the container on screen', async () => {
    renderPanel();
    const button = await screen.findByRole('button', { name: /download/i });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);

    await waitFor(() => expect(state.download).toHaveBeenCalledWith('sh-1'));
  });

  it('says so when the export fails instead of failing silently', async () => {
    state.download = vi.fn().mockRejectedValue(new Error('Export failed'));
    renderPanel();
    const button = await screen.findByRole('button', { name: /download/i });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);

    await waitFor(() => expect(toastError).toHaveBeenCalledWith('Export failed'));
  });
});
