/**
 * P6 - the reconciliation list, as a place to FIX things rather than read about them.
 *
 * The report this answers, verbatim: "tbh i am quite confused with the delivery schedule,
 * cause ya I know i need to fix this and that, but how can i fix it, idk". Every sentence in
 * this list stated a problem and offered nothing to press; the fix existed, twenty columns
 * sideways, in a table header. So what is pinned here is that each blocker code carries its
 * own action, that the action is the one that ends THAT problem, and that a reviewer who
 * cannot edit is offered none of them.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { buildColumnStates } from '../lib/scheduleTotals';
import type { ColumnState } from '../lib/scheduleTotals';
import { DeliveryScheduleReconciliationList } from './DeliveryScheduleReconciliationList';

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

const phases = [
  { id: 'ph1', area_group: 'TOWER', sequence: 1, label: 'Level 2 & 7', delivery_date: null },
];

/** One column per blocker code, so each row's action can be looked at on its own. */
function columns(): ColumnState[] {
  return buildColumnStates(
    [
      // Resolved, but the phases and the PO disagree: a quantity problem.
      {
        product_id: 'p1',
        product_code: 'SRTFV1001',
        product_name: 'Sensor Urinal Flush Valve',
        customer_code_raw: 'BUI-HB-SRTFV1001',
        resolution_source: 'code',
        reported_total: '16',
        po_qty: '16',
        product_index: 0,
      },
      // Never matched to anything.
      {
        product_id: null,
        product_code: null,
        product_name: null,
        customer_code_raw: 'BUI-HB-SRTWB7055',
        resolution_source: null,
        reported_total: '927',
        po_qty: null,
        product_index: 1,
      },
      // Matched, and the PO has never heard of it: usually the WRONG match.
      {
        product_id: 'p3',
        product_code: 'SRTWC8613-RL',
        product_name: 'One-Piece WC',
        customer_code_raw: 'BUI-HB-SRTWC8613-RL',
        resolution_source: 'code',
        reported_total: '40',
        po_qty: null,
        product_index: 2,
      },
    ],
    phases,
    [
      { phase_id: 'ph1', product_id: 'p1', product_index: 0, qty: '8' },
      { phase_id: 'ph1', product_id: null, product_index: 1, qty: '927' },
      { phase_id: 'ph1', product_id: 'p3', product_index: 2, qty: '40' },
    ],
  );
}

function renderList(overrides: Partial<React.ComponentProps<typeof DeliveryScheduleReconciliationList>> = {}) {
  const props = {
    columns: columns(),
    canEdit: true,
    poHref: '/project-sales/p1/purchase-orders/pv1',
    onJump: vi.fn(),
    onFixQuantities: vi.fn(),
    onResolveProduct: vi.fn(),
    ...overrides,
  };
  render(<DeliveryScheduleReconciliationList {...props} />);
  return props;
}

/** The row whose name button carries this label. */
function row(name: string) {
  const button = screen.getByRole('button', { name: `Go to ${name} in the schedule` });
  return within(button.closest('li') as HTMLElement);
}

beforeEach(() => {
  vi.clearAllMocks();
  getProductsForVariantSelect.mockResolvedValue([
    { id: 'p6', product_code: 'SRTWB7055', product_name: 'Counter-Top Basin' },
  ]);
});

describe('DeliveryScheduleReconciliationList', () => {
  it('is one row per column, not a nested list of blockers', () => {
    renderList();
    expect(within(screen.getByTestId('reconciliation-list')).getAllByRole('listitem'))
      .toHaveLength(3);
  });

  it('keeps the jump, as a real button that is not wrapping the other buttons', () => {
    const props = renderList();

    const jump = screen.getByRole('button', { name: 'Go to SRTFV1001 in the schedule' });
    fireEvent.click(jump);
    expect(props.onJump).toHaveBeenCalledWith('p1');

    // A button inside a button is invalid markup and unreachable by keyboard.
    Array.from(
      screen.getByTestId('reconciliation-list').querySelectorAll('button'),
    ).forEach((button) => {
      expect(button.parentElement?.closest('button')).toBeNull();
    });
  });

  it('offers the picker to a column that was never matched', () => {
    renderList();
    expect(
      row('BUI-HB-SRTWB7055').getByLabelText('Pick the product for BUI-HB-SRTWB7055'),
    ).toBeInTheDocument();
  });

  it('picks the product with the column index the API addresses it by', async () => {
    const props = renderList();

    fireEvent.click(
      row('BUI-HB-SRTWB7055').getByLabelText('Pick the product for BUI-HB-SRTWB7055'),
    );
    fireEvent.click(await screen.findByText('SRTWB7055'));

    await waitFor(() => expect(props.onResolveProduct).toHaveBeenCalledWith(1, 'p6'));
  });

  it("seeds the search with our code hiding inside the customer's", async () => {
    renderList();

    fireEvent.click(
      row('BUI-HB-SRTWB7055').getByLabelText('Pick the product for BUI-HB-SRTWB7055'),
    );

    // Not "BUI-HB-SRTWB7055", which matches no product code and would open on "No products
    // match", and not blank either.
    await waitFor(() =>
      expect(getProductsForVariantSelect).toHaveBeenCalledWith('SRTWB7055'),
    );
    expect(screen.getByPlaceholderText('Search...')).toHaveValue('SRTWB7055');
  });

  it('answers "not on the PO" with a different product first, and the PO second', () => {
    renderList();

    const notOnPo = row('SRTWC8613-RL');
    expect(
      notOnPo.getByLabelText('Pick a different product for BUI-HB-SRTWC8613-RL'),
    ).toBeInTheDocument();
    expect(notOnPo.getByRole('link', { name: /Open the PO to amend it/ })).toHaveAttribute(
      'href',
      '/project-sales/p1/purchase-orders/pv1',
    );
  });

  it('does not offer to re-pick a product that was never picked', () => {
    renderList();

    // The unmatched column carries not_on_po too, and its own blocker above already offers
    // the picker. Twice on one row is noise.
    const unmatched = row('BUI-HB-SRTWB7055');
    expect(unmatched.queryByLabelText(/Pick a different product/)).toBeNull();
    expect(unmatched.getByRole('link', { name: /Open the PO to amend it/ })).toBeInTheDocument();
  });

  it('leaves the PO out when this schedule was checked against no PO version', () => {
    renderList({ poHref: null });
    expect(screen.queryByRole('link', { name: /Open the PO/ })).toBeNull();
  });

  it('sends a quantity blocker to the column it has to be typed into', () => {
    const props = renderList();

    const quantities = row('SRTFV1001').getAllByRole('button', {
      name: 'Fix the quantities',
    });
    // Both the PO disagreement and the TOTAL QTY disagreement are fixed by the same typing.
    expect(quantities).toHaveLength(2);

    fireEvent.click(quantities[0]);
    expect(props.onFixQuantities).toHaveBeenCalledWith('p1');
  });

  it('offers no fix at all to a reviewer who cannot edit', () => {
    const props = renderList({ canEdit: false });

    expect(screen.queryByLabelText(/Pick the product/)).toBeNull();
    expect(screen.queryByLabelText(/Pick a different product/)).toBeNull();
    expect(screen.queryByRole('button', { name: 'Fix the quantities' })).toBeNull();
    expect(screen.queryByRole('link', { name: /Open the PO/ })).toBeNull();

    // The jump is not a fix, so it stays: reading the column is still allowed.
    fireEvent.click(screen.getByRole('button', { name: 'Go to SRTFV1001 in the schedule' }));
    expect(props.onJump).toHaveBeenCalledWith('p1');
  });
});
