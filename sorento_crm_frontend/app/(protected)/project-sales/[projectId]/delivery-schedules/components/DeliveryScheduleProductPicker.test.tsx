/**
 * P6 - what the picker opens with, and what it offers.
 *
 * Two things are pinned here. The search term: the customer prints OUR code inside THEIRS,
 * so searching a product catalogue for `BUI-HB-SRTWB7055` finds nothing and the picker opens
 * on "No products match", which reads as "the product does not exist"; the seed is the same
 * candidate the backend resolver already tries (`_code_candidates`), so the two agree about
 * what part of the printed code is ours. And the LIST: a schedule column has to land on a
 * line of the PO it was checked against, so the PO's own products are the list, not the
 * catalogue's thousands.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { POVersionLine } from '../../../_shared/types/poIntake.types';
import {
  DeliveryScheduleProductPicker,
  poProductOptions,
  productSearchSeed,
} from './DeliveryScheduleProductPicker';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const getProductsForVariantSelect = vi.fn();
vi.mock('@/app/(protected)/master-data-management/products/services/productService', () => ({
  getProductsForVariantSelect: (...args: unknown[]) => getProductsForVariantSelect(...args),
}));

describe('productSearchSeed', () => {
  it('strips the customer prefix off their code', () => {
    expect(productSearchSeed('BUI-HB-SRTWB7055')).toBe('SRTWB7055');
  });

  it('keeps a trailing part of the code that is part of the code', () => {
    // Not "RL": a two-letter suffix is a variant marker, not a product code, and it is
    // below the four characters the backend's own fuzzy probe will even consider.
    expect(productSearchSeed('BUI-HB-SRTWC8613-RL')).toBe('SRTWC8613-RL');
  });

  it('searches a code with no prefix as it is', () => {
    expect(productSearchSeed('SRTFV1001')).toBe('SRTFV1001');
  });

  it('asks for nothing when the column has no code at all', () => {
    expect(productSearchSeed(null)).toBe('');
    expect(productSearchSeed('   ')).toBe('');
  });
});

function line(overrides: Partial<POVersionLine> = {}): POVersionLine {
  return {
    id: 'l1',
    line_no: 1,
    stock_code_raw: 'SRTWC8613-RL',
    description_raw: 'ONE-PIECE WC',
    qty: '927',
    uom_raw: 'NOS',
    unit_price: '100.00',
    amount: '92700.00',
    arithmetic_ok: true,
    is_cancelled: false,
    resolved_product_id: 'p1',
    resolved_product_code: 'SRTWC8613-RL',
    resolution_source: 'code',
    ...overrides,
  };
}

describe('poProductOptions', () => {
  it('offers one option per product the PO orders', () => {
    expect(poProductOptions([line()])).toEqual([
      { value: 'p1', label: 'SRTWC8613-RL', description: 'ONE-PIECE WC' },
    ]);
  });

  it('leaves out a line no product was ever resolved for', () => {
    // There is nothing to pick: the picker writes a product id, and this line has none.
    expect(
      poProductOptions([line({ resolved_product_id: null, resolved_product_code: null })]),
    ).toEqual([]);
  });

  it('counts the same product ordered on two lines once', () => {
    const options = poProductOptions([
      line(),
      line({ id: 'l2', line_no: 2, description_raw: 'ONE-PIECE WC (LEVEL 7)' }),
    ]);
    expect(options).toHaveLength(1);
  });

  it('falls back to what the document printed when the resolver named no code', () => {
    const options = poProductOptions([
      line({ resolved_product_code: null, stock_code_raw: 'WC-8613' }),
    ]);
    expect(options[0].label).toBe('WC-8613');
  });
});

const PO_OPTIONS = [
  { value: 'p1', label: 'SRTWC8613-RL', description: 'ONE-PIECE WC' },
  { value: 'p2', label: 'SRTFV1001', description: 'SENSOR URINAL FLUSH VALVE' },
];

function renderPicker(
  overrides: Partial<React.ComponentProps<typeof DeliveryScheduleProductPicker>> = {},
) {
  const props = {
    idPrefix: 'test',
    columnIndex: 0,
    customerCode: null,
    poOptions: PO_OPTIONS,
    onPick: vi.fn(),
    ...overrides,
  };
  render(<DeliveryScheduleProductPicker {...props} />);
  return props;
}

/** The field variant's trigger, named after what pressing it does. */
function open(name = 'Pick the product for column 1') {
  fireEvent.click(screen.getByLabelText(name));
}

beforeEach(() => {
  vi.clearAllMocks();
  getProductsForVariantSelect.mockResolvedValue([
    { id: 'p6', product_code: 'SRTWB7055', product_name: 'Counter-Top Basin' },
  ]);
});

describe('DeliveryScheduleProductPicker', () => {
  it('offers the PO its own products, and asks the catalogue for nothing', async () => {
    renderPicker();
    open();

    expect(await screen.findByText('SRTWC8613-RL')).toBeInTheDocument();
    expect(screen.getByText('SRTFV1001')).toBeInTheDocument();
    expect(getProductsForVariantSelect).not.toHaveBeenCalled();
  });

  it('picks the product the reviewer chose off the PO', async () => {
    const props = renderPicker();
    open();

    fireEvent.click(await screen.findByText('SRTFV1001'));
    await waitFor(() => expect(props.onPick).toHaveBeenCalledWith('p2'));
  });

  it('narrows the PO list by what is typed, code or description', async () => {
    renderPicker();
    open();
    await screen.findByText('SRTWC8613-RL');

    fireEvent.change(screen.getByPlaceholderText('Search...'), {
      target: { value: 'urinal' },
    });

    await waitFor(() => expect(screen.queryByText('SRTWC8613-RL')).toBeNull());
    expect(screen.getByText('SRTFV1001')).toBeInTheDocument();
    expect(getProductsForVariantSelect).not.toHaveBeenCalled();
  });

  it('never leaves the PO, however narrow the search gets', async () => {
    // The catalogue used to be appended when the PO matched nothing, and two typed letters
    // brought thousands of items back beside the PO's own - the exact thing the PO list is
    // for. A product the PO does not order is fixed by amending the PO, not by picking
    // another product it does not order either.
    renderPicker();
    open();
    await screen.findByText('SRTWC8613-RL');

    fireEvent.change(screen.getByPlaceholderText('Search...'), {
      target: { value: 'SRTWB7055' },
    });

    expect(await screen.findByText('No PO line matches')).toBeInTheDocument();
    expect(getProductsForVariantSelect).not.toHaveBeenCalled();
  });

  it('searches the catalogue when this schedule was checked against no PO', async () => {
    renderPicker({ poOptions: [] });
    open();

    expect(await screen.findByText('SRTWB7055')).toBeInTheDocument();
    await waitFor(() => expect(getProductsForVariantSelect).toHaveBeenCalled());
  });

  it('opens on the whole PO, unnarrowed, even for a column with a printed code', async () => {
    // The seed would be 'SRTWB7055', which this PO does not order - which is exactly why the
    // column does not reconcile. Applied here it opens the picker on an empty list and the
    // reviewer has to clear the box to reach the lines they came to choose from.
    renderPicker({ customerCode: 'BUI-HB-SRTWB7055' });
    open('Pick the product for BUI-HB-SRTWB7055');

    expect(screen.getByPlaceholderText('Search...')).toHaveValue('');
    expect(await screen.findByText('SRTWC8613-RL')).toBeInTheDocument();
    expect(screen.getByText('SRTFV1001')).toBeInTheDocument();
    expect(getProductsForVariantSelect).not.toHaveBeenCalled();
  });

  it("seeds the catalogue search with our code hiding inside the customer's", async () => {
    // No PO list, so the catalogue is the only list there is, and unnarrowed it is thousands
    // of items. The seed is the same candidate the backend resolver tries.
    renderPicker({ poOptions: [], customerCode: 'BUI-HB-SRTWB7055' });
    open('Pick the product for BUI-HB-SRTWB7055');

    expect(screen.getByPlaceholderText('Search...')).toHaveValue('SRTWB7055');
    await waitFor(() =>
      expect(getProductsForVariantSelect).toHaveBeenCalledWith('SRTWB7055'),
    );
  });
});
