/**
 * P6 - the reconciliation table, as a place to FIX things rather than read about them.
 *
 * The report this answers, verbatim: "tbh i am quite confused with the delivery schedule,
 * cause ya I know i need to fix this and that, but how can i fix it, idk". Every sentence in
 * this section stated a problem and offered nothing to press; the fix existed, twenty columns
 * sideways, in a table header. So what is pinned here is that each row carries its own action,
 * that the action is the one that ends THAT row's worst problem, that the three numbers are in
 * their own columns where they can be compared down the page, and that a reviewer who cannot
 * edit is offered none of the actions.
 *
 * It is the shared DataGrid, so `useListingColumnPreferences` is stubbed - under jsdom nothing
 * answers its fetch and the grid would render skeletons instead of rows (CLAUDE.md).
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

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

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
    poOptions: [],
    onJump: vi.fn(),
    onFixQuantities: vi.fn(),
    onResolveProduct: vi.fn(),
    ...overrides,
  };
  render(<DeliveryScheduleReconciliationList {...props} />);
  return props;
}

/** The table row whose name button carries this label. */
function row(name: string) {
  const button = screen.getByRole('button', { name: `Go to ${name} in the schedule` });
  return within(button.closest('tr') as HTMLElement);
}

/** Body rows only: the header row is a row too, as far as the DOM is concerned. */
function bodyRows() {
  return screen
    .getAllByRole('row')
    .filter((node) => node.querySelector('td') !== null);
}

beforeEach(() => {
  vi.clearAllMocks();
  getProductsForVariantSelect.mockResolvedValue([
    { id: 'p6', product_code: 'SRTWB7055', product_name: 'Counter-Top Basin' },
  ]);
});

describe('DeliveryScheduleReconciliationList', () => {
  it('is one row per column, with the three numbers in their own columns', () => {
    renderList();

    expect(bodyRows()).toHaveLength(3);
    ['Code', 'Status', 'Schedule qty', 'Reported total', 'PO qty', 'Problem', 'Action'].forEach(
      (heading) => expect(screen.getByText(heading)).toBeInTheDocument(),
    );

    // The flush valve's own numbers, each in its own cell rather than inside a sentence.
    const cells = row('SRTFV1001').getAllByRole('cell');
    expect(cells[2]).toHaveTextContent('8');
    expect(cells[3]).toHaveTextContent('16');
    expect(cells[4]).toHaveTextContent('16');
  });

  it('says what a missing number means instead of printing a dash', () => {
    renderList();

    // A column the PO never ordered is not a column that ordered nothing.
    expect(row('SRTWC8613-RL').getByText('Not on the PO')).toBeInTheDocument();
  });

  it('names each row state once, in colour', () => {
    const withWarning = columns();
    withWarning[0] = {
      ...withWarning[0],
      blockers: [],
      reconciled: true,
      warning: 'Matched by description, not by code.',
    };
    renderList({ columns: withWarning });

    expect(row('SRTFV1001').getByText('Warning')).toBeInTheDocument();
    expect(
      row('SRTFV1001').getByTestId('reconciliation-warning'),
    ).toHaveTextContent('Matched by description, not by code.');
    // A warning is not work: nothing is asked of the reviewer, not even a dismissal.
    expect(row('SRTFV1001').queryByRole('button', { name: 'Fix the quantities' })).toBeNull();
    expect(
      row('SRTFV1001').queryByRole('button', { name: 'Dismiss as false signal' }),
    ).toBeNull();

    expect(row('SRTWC8613-RL').getByText('Blocked')).toBeInTheDocument();
  });

  it('truncates the problem sentence but keeps the whole of it reachable', () => {
    renderList();

    // The price of a table. The numbers the sentence quotes are in their own columns, so
    // what is cut is the wording, and `title` still carries all of it.
    const detail = row('SRTFV1001').getAllByTestId('reconciliation-detail')[0];
    expect(String(detail.className)).toContain('truncate');
    expect(detail).toHaveAttribute('title', detail.textContent);
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

  it("seeds the catalogue search with our code hiding inside the customer's", async () => {
    // No PO list here, so the catalogue is the only list there is and the seed earns its
    // place: not "BUI-HB-SRTWB7055", which matches no product code, and not blank either.
    renderList();

    fireEvent.click(
      row('BUI-HB-SRTWB7055').getByLabelText('Pick the product for BUI-HB-SRTWB7055'),
    );

    await waitFor(() =>
      expect(getProductsForVariantSelect).toHaveBeenCalledWith('SRTWB7055'),
    );
    expect(screen.getByPlaceholderText('Search...')).toHaveValue('SRTWB7055');
  });

  it('answers "not on the PO" by correcting the product, and does not link the PO per row', () => {
    renderList();

    const notOnPo = row('SRTWC8613-RL');
    expect(
      notOnPo.getByLabelText('Pick a different product for BUI-HB-SRTWC8613-RL'),
    ).toBeInTheDocument();
    // Amending the PO is one action for the whole screen and lives in the header gear menu.
    // A link per row put it three times on one section, next to sentences it does not answer.
    expect(screen.queryByRole('link', { name: /PO/ })).toBeNull();
  });

  it('does not offer to re-pick a product that was never picked', () => {
    renderList();

    // The unmatched column carries not_on_po too, and identifying it comes first, so its
    // row offers "Pick the product" rather than "Pick a different product".
    const unmatched = row('BUI-HB-SRTWB7055');
    expect(unmatched.queryByLabelText(/Pick a different product/)).toBeNull();
    expect(unmatched.getByLabelText(/Pick the product/)).toBeInTheDocument();
  });

  it('sends a quantity blocker to the column it has to be typed into', () => {
    const props = renderList();

    // ONE action per row, not one per sentence: both of the flush valve's disagreements are
    // fixed by the same typing, and two identical buttons read as two jobs.
    const quantities = row('SRTFV1001').getAllByRole('button', {
      name: 'Fix the quantities',
    });
    expect(quantities).toHaveLength(1);

    fireEvent.click(quantities[0]);
    expect(props.onFixQuantities).toHaveBeenCalledWith('p1');
  });

  /**
   * "You should let me dismiss the warning if it is a false signal by the system."
   *
   * The check reads somebody else's paper and is sometimes wrong about a column that is
   * fine. Until now the only way past it was the whole-sheet acknowledgement at confirm,
   * which names no column and is taken at the last moment.
   */
  describe('dismissing a false signal', () => {
    it('takes a reason and reports the column index the API addresses', () => {
      const onDismissColumn = vi.fn();
      renderList({ onDismissColumn });

      fireEvent.click(
        row('SRTFV1001').getByRole('button', { name: 'Dismiss as false signal' }),
      );
      fireEvent.change(
        row('SRTFV1001').getByLabelText('Why the check is wrong about SRTFV1001'),
        { target: { value: 'Customer confirmed 8 by email' } },
      );
      fireEvent.click(row('SRTFV1001').getByRole('button', { name: 'Dismiss' }));

      expect(onDismissColumn).toHaveBeenCalledWith(0, true, 'Customer confirmed 8 by email');
    });

    it('will not save a dismissal with no reason', () => {
      const onDismissColumn = vi.fn();
      renderList({ onDismissColumn });

      fireEvent.click(
        row('SRTFV1001').getByRole('button', { name: 'Dismiss as false signal' }),
      );
      const save = row('SRTFV1001').getByRole('button', { name: 'Dismiss' });
      expect(save).toBeDisabled();

      fireEvent.click(save);
      expect(onDismissColumn).not.toHaveBeenCalled();
    });

    it('shows a dismissed column as overruled, with the reason and a way back', () => {
      const onDismissColumn = vi.fn();
      const dismissed = columns();
      dismissed[0] = {
        ...dismissed[0],
        reconciled: true,
        dismissed: true,
        dismissedReason: 'Customer confirmed 8 by email',
        dismissedByName: 'Yana',
      };
      renderList({ columns: dismissed, onDismissColumn });

      expect(row('SRTFV1001').getByText('Dismissed')).toBeInTheDocument();
      const line = row('SRTFV1001').getByTestId('reconciliation-dismissed');
      expect(line).toHaveTextContent('Dismissed as a false signal by Yana');
      expect(line).toHaveTextContent('Customer confirmed 8 by email');
      // What the check found is still on screen: the verdict was overruled, not withdrawn.
      expect(row('SRTFV1001').getAllByTestId('reconciliation-detail').length).toBeGreaterThan(0);
      // And nothing is asked of the reviewer any more.
      expect(row('SRTFV1001').queryByRole('button', { name: 'Fix the quantities' })).toBeNull();

      fireEvent.click(row('SRTFV1001').getByRole('button', { name: 'Undo' }));
      expect(onDismissColumn).toHaveBeenCalledWith(0, false);
    });

    it('shows the reason but no way to change it on a confirmed schedule', () => {
      const dismissed = columns();
      dismissed[0] = {
        ...dismissed[0],
        reconciled: true,
        dismissed: true,
        dismissedReason: 'Customer confirmed 8 by email',
        dismissedByName: 'Yana',
      };
      renderList({ columns: dismissed, canEdit: false, onDismissColumn: vi.fn() });

      expect(screen.getByTestId('reconciliation-dismissed')).toHaveTextContent(
        'Customer confirmed 8 by email',
      );
      expect(screen.queryByRole('button', { name: 'Undo' })).toBeNull();
      expect(screen.queryByRole('button', { name: 'Dismiss as false signal' })).toBeNull();
    });
  });

  it('offers no fix at all to a reviewer who cannot edit', () => {
    const props = renderList({ canEdit: false });

    expect(screen.queryByLabelText(/Pick the product/)).toBeNull();
    expect(screen.queryByLabelText(/Pick a different product/)).toBeNull();
    expect(screen.queryByRole('button', { name: 'Fix the quantities' })).toBeNull();
    expect(screen.queryByRole('link', { name: /PO/ })).toBeNull();

    // The jump is not a fix, so it stays: reading the column is still allowed.
    fireEvent.click(screen.getByRole('button', { name: 'Go to SRTFV1001 in the schedule' }));
    expect(props.onJump).toHaveBeenCalledWith('p1');
  });
});
