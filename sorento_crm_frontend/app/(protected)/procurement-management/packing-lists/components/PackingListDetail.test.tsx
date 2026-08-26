/**
 * A mixed container has no supplier on its header, and this page used to say "No supplier"
 * about a container two factories had loaded. The factories are on the LINES; the page reads
 * them from there, and names each line's factory next to it so a line can be traced back to
 * the packing list it came off.
 *
 * The line response carries `supplier_id` only, so the names come from the shared supplier
 * select - a UUID is never shown.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';

const searchParams = { value: new URLSearchParams() };

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => searchParams.value,
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

const state = { packingList: null as unknown };

vi.mock('../hooks/usePackingLists', () => ({
  usePackingList: () => ({ data: state.packingList, isLoading: false }),
  useDeletePackingList: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdatePackingList: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

vi.mock('../../suppliers/hooks/useSupplierSelectQuery', () => ({
  useSupplierSelectQuery: () => ({
    data: [
      { id: 'sup-a', supplier_code: '400-K029', supplier_name: 'KAILU HARDWARE FACTORY' },
      { id: 'sup-b', supplier_code: '400-C011', supplier_name: 'CAIZHOU SANITARY' },
    ],
  }),
}));

vi.mock('@/app/(protected)/resource-management/attachments/hooks/useAttachments', () => ({
  useDownloadAttachment: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock('@/app/(protected)/resource-management/attachments/services/attachmentService', () => ({
  getAttachmentPreviewUrl: vi.fn(),
}));

vi.mock('./PackingListNavigation', () => ({ default: () => null }));
vi.mock('./packing-list-delete-dialog', () => ({ default: () => null }));
vi.mock('./ClearanceDeliveryCard', () => ({ default: () => null }));
vi.mock('@/components/common/LinkAttachmentBrowserDialog', () => ({ default: () => null }));

import PackingListDetail from './PackingListDetail';

/** Two factories on the lines, nobody on the header - the shape the fix is about. */
function mixedContainer(over: Record<string, unknown> = {}) {
  return {
    id: 'pl-1',
    shipment_number: 'SPO-0042',
    supplier_id: null,
    supplier: undefined,
    shipment_date: '2026-07-30',
    shipping_container_number: 'FSCU8103365',
    shipment_status: 'in_transit',
    created_at: '2026-07-30',
    updated_at: '2026-07-30',
    synced_to_excel: false,
    shipment_lines: [
      {
        id: 'l-1',
        shipment_id: 'pl-1',
        product_id: 'p-1',
        quantity_shipped: 490,
        cartons_count: 86,
        cbm: '12.5',
        supplier_id: 'sup-a',
        product: { id: 'p-1', product_code: 'SRTWT7443', product_name: 'Basin Mixer Tall' },
      },
      {
        id: 'l-2',
        shipment_id: 'pl-1',
        product_id: 'p-2',
        quantity_shipped: 900,
        cartons_count: 55,
        cbm: 7.25,
        supplier_id: 'sup-b',
        product: { id: 'p-2', product_code: 'MCHWT1200', product_name: 'Shower Set' },
      },
      {
        id: 'l-3',
        shipment_id: 'pl-1',
        product_id: 'p-3',
        quantity_shipped: 120,
        cartons_count: 30,
        supplier_id: null,
        product: { id: 'p-3', product_code: 'SRTBT2200', product_name: 'Bath Tub 1700' },
      },
    ],
    ...over,
  };
}

function renderDetail() {
  return render(<PackingListDetail packingListId="pl-1" />);
}

beforeEach(() => {
  vi.clearAllMocks();
  searchParams.value = new URLSearchParams();
  state.packingList = mixedContainer();
});

describe('PackingListDetail - who loaded this container', () => {
  it('names every factory on the lines when the header names none', () => {
    state.packingList = mixedContainer();
    renderDetail();

    expect(
      screen.getByText(/KAILU HARDWARE FACTORY, CAIZHOU SANITARY/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/No supplier/)).not.toBeInTheDocument();
  });

  it('still says "No supplier" when nothing on the container claims a factory', () => {
    const list = mixedContainer();
    list.shipment_lines.forEach((l) => {
      l.supplier_id = null;
    });
    state.packingList = list;
    renderDetail();

    expect(screen.getByText(/No supplier/)).toBeInTheDocument();
  });

  it("keeps the header's own supplier when the container is a single factory's", () => {
    state.packingList = mixedContainer({
      supplier_id: 'sup-a',
      supplier: {
        id: 'sup-a',
        supplier_code: '400-K029',
        supplier_name: 'KAILU HARDWARE FACTORY',
      },
    });
    renderDetail();

    expect(screen.getByText(/KAILU HARDWARE FACTORY •/)).toBeInTheDocument();
  });
});

describe('PackingListDetail - the line table', () => {
  beforeEach(() => {
    // The lines tab is the one under test; Radix only mounts the active tab's body.
    searchParams.value = new URLSearchParams('tab=lines');
  });

  it('names the factory that loaded each line', () => {
    renderDetail();

    const header = screen.getByRole('columnheader', { name: 'Supplier' });
    expect(header).toBeInTheDocument();

    const kailuLine = screen.getByText('SRTWT7443').closest('tr') as HTMLElement;
    expect(within(kailuLine).getByText('KAILU HARDWARE FACTORY')).toBeInTheDocument();
    const caizhouLine = screen.getByText('MCHWT1200').closest('tr') as HTMLElement;
    expect(within(caizhouLine).getByText('CAIZHOU SANITARY')).toBeInTheDocument();
  });

  it('leaves a line nobody has claimed blank rather than guessing an owner', () => {
    renderDetail();

    const unclaimed = screen.getByText('SRTBT2200').closest('tr') as HTMLElement;
    // The supplier cell, second after the product - "-" also stands for an unallocated
    // quantity further along the row.
    expect(unclaimed.querySelectorAll('td')[1]).toHaveTextContent('-');
    expect(within(unclaimed).queryByText(/FACTORY|SANITARY/)).not.toBeInTheDocument();
  });
});

describe('F6 - the container states how much room it takes', () => {
  beforeEach(() => {
    searchParams.value = new URLSearchParams('tab=lines');
  });

  it('shows cartons and CBM per line, decimal on the wire included (AC-F2)', () => {
    renderDetail();

    expect(screen.getByRole('columnheader', { name: 'CBM' })).toBeInTheDocument();
    const kailuLine = screen.getByText('SRTWT7443').closest('tr') as HTMLElement;
    expect(within(kailuLine).getByText('12.5')).toBeInTheDocument();
    expect(within(kailuLine).getByText('86')).toBeInTheDocument();
  });

  it('reads "-" on a line nobody measured, never 0 (AC-F2)', () => {
    renderDetail();

    const unmeasured = screen.getByText('SRTBT2200').closest('tr') as HTMLElement;
    // The CBM cell is the fifth: product, supplier, quantity, cartons, cbm.
    expect(unmeasured.querySelectorAll('td')[4]).toHaveTextContent('-');
  });

  it('totals the volume under the column and counts what is unmeasured', () => {
    renderDetail();

    const total = screen.getByText('Total').closest('tr') as HTMLElement;
    expect(within(total).getByText('19.75')).toBeInTheDocument();
    expect(within(total).getByText('(1 unmeasured)')).toBeInTheDocument();
    // Quantity and cartons total too, so the footer answers the whole row.
    expect(within(total).getByText('1510')).toBeInTheDocument();
    expect(within(total).getByText('171')).toBeInTheDocument();
  });
});
