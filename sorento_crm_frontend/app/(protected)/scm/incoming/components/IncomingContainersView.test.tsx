/**
 * The incoming-containers screen.
 *
 * Two things here would mislead: an upload that does not say WHOSE lines it is (the server
 * refuses it, and an unowned upload is what used to wipe the first factory's lines off a
 * mixed container), and a row that trades the shipment number away for the factory names -
 * the shipment number is what the SPO and the GRN are keyed on, so both have to be readable.
 *
 * SearchableSelect is mocked to a native <select>: the real one is a Radix popover + cmdk
 * list, which is not deterministic under jsdom. The three panels are stubbed - each has its
 * own test file, and here they only have to not explode.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
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

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
  }: {
    value: string;
    onChange: (v: string) => void;
    options: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <select
      aria-label={placeholder ?? 'select'}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">{placeholder ?? ''}</option>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

const state = {
  suppliers: [
    { value: 'sup-a', label: 'KAILU HARDWARE FACTORY' },
    { value: 'sup-b', label: 'CAIZHOU SANITARY' },
  ],
  shipments: [] as unknown[],
};

vi.mock('../../hooks/useFulfilment', () => ({
  useFulfilmentSuppliers: () => ({ data: state.suppliers, isLoading: false }),
}));

vi.mock('../../services/fulfilmentService', () => ({
  getIncomingShipments: () => Promise.resolve(state.shipments),
}));

vi.mock('./ConsolidatedPackingListPanel', () => ({
  ConsolidatedPackingListPanel: () => null,
}));
vi.mock('./AllocationPanel', () => ({ AllocationPanel: () => null }));
vi.mock('./PackingListUploadDialog', () => ({
  PackingListUploadDialog: ({
    supplierId,
    supplierName,
  }: {
    supplierId: string | null;
    supplierName?: string | null;
  }) => (
    <div data-testid="upload-dialog" data-supplier-id={supplierId ?? ''}>
      {supplierName ?? ''}
    </div>
  ),
}));

import { IncomingContainersView } from './IncomingContainersView';

function shipment(over: Record<string, unknown> = {}) {
  return {
    shipment_id: 'sh-1',
    shipment_number: 'SPO-0042',
    container_no: 'FSCU8103365',
    bl_no: null,
    status: 'in_transit',
    lines: 21,
    created_at: null,
    suppliers: [
      { supplier_id: 'sup-a', supplier_code: '400-K029', supplier_name: 'KAILU HARDWARE FACTORY' },
      { supplier_id: 'sup-b', supplier_code: '400-C011', supplier_name: 'CAIZHOU SANITARY' },
    ],
    ...over,
  };
}

function renderView() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <IncomingContainersView />
    </QueryClientProvider>,
  );
}

function uploadButton() {
  return screen.getByRole('button', { name: /upload packing list/i });
}

beforeEach(() => {
  state.shipments = [];
});

describe('IncomingContainersView - the upload needs a factory', () => {
  it('refuses to open the upload until a supplier is chosen, and says why', () => {
    renderView();

    expect(uploadButton()).toBeDisabled();
    expect(uploadButton()).toHaveAttribute('title', 'Choose a supplier first');
  });

  it('opens once a supplier is chosen, and names it for the dialog', () => {
    renderView();

    fireEvent.change(screen.getByLabelText('Choose a supplier'), { target: { value: 'sup-a' } });

    expect(uploadButton()).toBeEnabled();
    expect(uploadButton()).not.toHaveAttribute('title');
    // The dialog prints the factory the lines will be filed under, so it is never a guess.
    const dialog = screen.getByTestId('upload-dialog');
    expect(dialog).toHaveAttribute('data-supplier-id', 'sup-a');
    expect(dialog).toHaveTextContent('KAILU HARDWARE FACTORY');
  });
});

describe('IncomingContainersView - what a container row says', () => {
  it('keeps the shipment number when the factories are known', async () => {
    state.shipments = [shipment()];
    renderView();

    expect(await screen.findByText('FSCU8103365')).toBeInTheDocument();
    expect(
      screen.getByText('SPO-0042 · KAILU HARDWARE FACTORY, CAIZHOU SANITARY'),
    ).toBeInTheDocument();
  });

  it('does not repeat the container number when the shipment is named after it', async () => {
    state.shipments = [shipment({ shipment_number: 'FSCU8103365' })];
    renderView();

    expect(
      await screen.findByText('KAILU HARDWARE FACTORY, CAIZHOU SANITARY'),
    ).toBeInTheDocument();
  });

  it('still says a container has no number yet when no factory is known', async () => {
    state.shipments = [shipment({ container_no: null, suppliers: [] })];
    renderView();

    expect(await screen.findByText('No container number yet')).toBeInTheDocument();
  });

  it('says a container has no shipment number rather than printing nothing', async () => {
    // A blank second line reads as a row that failed to load, and the missing shipment
    // number is exactly what someone chasing an SPO needs to be told.
    state.shipments = [shipment({ shipment_number: null, suppliers: [] })];
    renderView();

    expect(await screen.findByText('FSCU8103365')).toBeInTheDocument();
    expect(screen.getByText('No shipment number')).toBeInTheDocument();
  });

  it('names a container that has neither number, so the row can still be picked', async () => {
    state.shipments = [
      shipment({ container_no: null, shipment_number: null, suppliers: [] }),
    ];
    renderView();

    expect(await screen.findByText('Unnumbered container')).toBeInTheDocument();
    expect(screen.getByText('No container number yet')).toBeInTheDocument();
  });
});
