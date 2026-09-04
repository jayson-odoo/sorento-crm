/**
 * S10 - the container as one list.
 *
 * What is asserted is what Ms Tee would be misled by: a factory shown without its subtotal and
 * a split that prints one company and leaves the other to be inferred.
 *
 * The panel prints the shipment and nothing else since R20 - the comparison against the
 * loading plan (derived remarks, the not-packed list, the "vs plan of" chip) was removed, and
 * so were the tests that asserted it.
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
vi.mock('@/lib/toast', () => ({
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
        lines: [KAILU_LINE, MOCHA_LINE],
        subtotal: { lines: 2, qty: 1390, cartons: 141, cbm: 9.4123 },
      },
      {
        supplier_id: 'sup-b',
        supplier_code: '400-C011',
        supplier_name: 'CAIZHOU SANITARY',
        lines: [CAIZHOU_LINE],
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

  it("shows the supplier's own description, the product name when the line has none (S9)", async () => {
    state.getList = vi.fn().mockResolvedValue(
      packingList({
        factories: [
          {
            supplier_id: 'sup-a',
            supplier_code: '400-K029',
            supplier_name: 'KAILU HARDWARE FACTORY',
            lines: [{ ...KAILU_LINE, description: '连体马桶' }, MOCHA_LINE],
            subtotal: { lines: 2, qty: 1390, cartons: 141, cbm: 9.4123 },
          },
        ],
      }),
    );
    renderPanel();

    // `build()` already resolves this pair, so this is the same value both ways -
    // KAILU's own wording where the line carries one, MOCHA's product name where it does
    // not (a payload built before this field existed).
    expect(await screen.findByText('连体马桶')).toBeInTheDocument();
    expect(screen.getByText('Shower Set')).toBeInTheDocument();
    expect(screen.queryByText('Basin Mixer Tall')).not.toBeInTheDocument();
  });

  it("prints the supplier's own remark, and nothing derived beside it", async () => {
    renderPanel();

    expect(await screen.findByText('Packed on two pallets')).toBeInTheDocument();
    // R20: the document prints the shipment. Our comparison against the loading plan is
    // not a remark the factory wrote, and it is no longer printed at all.
    expect(screen.queryByText(/Loading plan asked/)).not.toBeInTheDocument();
    expect(screen.queryByText('Not on the loading plan')).not.toBeInTheDocument();
    expect(screen.queryByText(/not packed/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/plan/i)).not.toBeInTheDocument();
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

  it('qualifies a cbm total the payload only knows part of', async () => {
    // A sum over 2 of 3 lines looks exactly like a sum over all 3, and it is the figure the
    // container gets planned against.
    state.getList = vi.fn().mockResolvedValue(
      packingList({
        total: { lines: 3, qty: 1510, cartons: 171, cbm: 9.4123, cbm_known_lines: 2 },
      }),
    );
    renderPanel();

    const footer = within(await screen.findByTestId('packing-list-footer'));
    expect(footer.getByText('1,510 qty · 171 ctn · 9.4123 cbm')).toBeInTheDocument();
    expect(footer.getByText('(2/3 lines)')).toBeInTheDocument();
    expect(footer.getByTitle('CBM known for 2 of 3 lines')).toBeInTheDocument();
  });

  it('leaves a cbm total unqualified when every line is measured', async () => {
    state.getList = vi.fn().mockResolvedValue(
      packingList({
        total: { lines: 3, qty: 1510, cartons: 171, cbm: 9.4123, cbm_known_lines: 3 },
        factories: [
          {
            supplier_id: 'sup-a',
            supplier_code: '400-K029',
            supplier_name: 'KAILU HARDWARE FACTORY',
            lines: [KAILU_LINE, MOCHA_LINE],
            subtotal: { lines: 2, qty: 1390, cartons: 141, cbm: 9.4123, cbm_known_lines: 2 },
          },
        ],
      }),
    );
    renderPanel();

    expect(await screen.findByText('9.4123 cbm')).toBeInTheDocument();
    expect(screen.queryByText(/\d+\/\d+ lines/)).not.toBeInTheDocument();
    expect(screen.queryByTitle(/CBM known for/)).not.toBeInTheDocument();
  });

  it('downloads the workbook for the container on screen', async () => {
    renderPanel();
    const button = await screen.findByRole('button', { name: /download/i });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);

    // Named after the container, never the shipment id: the fallback filename is what the
    // workbook is called when the server sends no Content-Disposition.
    await waitFor(() => expect(state.download).toHaveBeenCalledWith('sh-1', 'FSCU8103365'));
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
