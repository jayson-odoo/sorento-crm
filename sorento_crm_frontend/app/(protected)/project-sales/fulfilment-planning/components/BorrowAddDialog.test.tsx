/**
 * Stage 1C - adding a Borrow from a listed candidate (AC-B09, AC-B10), as amended by
 * PLAN-fulfilment-planning-from-autocount-so.md 13.11.
 *
 * Borrowing takes exactly one approval: the CS actor who confirms the sales order, with the
 * donor's impact in front of them and a reason nobody can skip. What the captain found
 * missing was the donor's OWN position - "before I decide to borrow, I need to know I am not
 * hurting them, so you need to let me know also what's their available, SO qty, SPO and PO
 * qty ... and what's the impact of borrowing. I assume this list is ranked by
 * recommendation, is it?"
 *
 * So what is pinned here is the donor TABLE (AutoCount's columns, in the server's ranked
 * order, with the recommended donor flagged), that the impact of the typed quantity is
 * stated and updates as it is typed, that a donor the borrow would leave short says so in
 * red and names the Order Inquiry it will raise, and that Add stays shut until a reason has
 * actually been typed.
 */
import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { BorrowCandidate } from '../../_shared/types/fulfilmentPlanning.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

import { BorrowAddDialog } from './BorrowAddDialog';

const WH_HQ = 'a1000000-0000-4000-8000-000000000002';
const WH_JB = 'a1000000-0000-4000-8000-000000000004';
const DONOR_PROJECT = 'b2000000-0000-4000-8000-000000000001';

/** The donor the ranking put first: nothing owed against its 80, so it keeps 60 of them. */
const OTHER_LOCATION: BorrowCandidate = {
  source: 'other_location',
  warehouse_code: 'HQ',
  warehouse_id: WH_HQ,
  free_qty: '80',
  qty_on_hand: '80',
  so_qty: '0',
  spo_qty: '0',
  available_qty: '80',
  qty_free: '80',
  qty_committed: '140',
  need_qty: '20',
  available_after_need: '60',
  recommended: true,
  donor_impact: { free_before: '80', free_after_full_borrow: '0', committed_qty: '140' },
};

/** Second: 50 free, but the book has sold 60 of its 70, so meeting the 20 leaves it short. */
const OTHER_PROJECT: BorrowCandidate = {
  source: 'other_project',
  warehouse_code: 'JB',
  warehouse_id: WH_JB,
  donor_project_ref: 'PRJ-0052 Seri Emas Phase 2',
  donor_project_id: DONOR_PROJECT,
  free_qty: '50',
  qty_on_hand: '70',
  so_qty: '60',
  spo_qty: '0',
  available_qty: '10',
  qty_free: '50',
  qty_committed: '50',
  need_qty: '20',
  available_after_need: '-10',
  recommended: false,
  donor_impact: { free_before: '50', free_after_full_borrow: '10', committed_qty: '50' },
};

const onAdd = vi.fn();
const onDone = vi.fn();

function renderDialog(candidates: BorrowCandidate[] = [OTHER_LOCATION, OTHER_PROJECT]) {
  return render(
    <BorrowAddDialog
      lineNo={2}
      itemCode="SRT501-CP"
      candidates={candidates}
      onDone={onDone}
      onAdd={onAdd}
    />,
  );
}

function headings(): string[] {
  return within(screen.getByTestId('borrow-donor-table'))
    .getAllByRole('columnheader')
    .map((cell) => cell.textContent?.trim() ?? '');
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('BorrowAddDialog', () => {
  it('names the line and the item it is borrowing for', () => {
    renderDialog();

    expect(screen.getByText('Borrow for line 2')).toBeInTheDocument();
    expect(screen.getByText('SRT501-CP')).toBeInTheDocument();
  });

  it('says "This item" rather than nothing when the line carries no item code', () => {
    render(
      <BorrowAddDialog
        lineNo={2}
        itemCode={null}
        candidates={[OTHER_LOCATION]}
        onDone={onDone}
        onAdd={onAdd}
      />,
    );

    expect(screen.getByText('This item')).toBeInTheDocument();
  });

  it("tabulates every donor under AutoCount's own column names", () => {
    renderDialog();

    expect(headings()).toEqual([
      'Source',
      'On hand',
      'SO qty',
      'SPO qty',
      'Available',
      'Free',
      'Committed',
      'After borrow',
    ]);
  });

  it("states a donor's whole position on its own row", () => {
    renderDialog();

    const row = screen.getByTestId('borrow-donor-JB');
    expect(within(row).getByTestId('borrow-cell-on-hand-JB')).toHaveTextContent('70');
    expect(within(row).getByTestId('borrow-cell-so-JB')).toHaveTextContent('60');
    expect(within(row).getByTestId('borrow-cell-spo-JB')).toHaveTextContent('0');
    expect(within(row).getByTestId('borrow-cell-available-JB')).toHaveTextContent('10');
    expect(within(row).getByTestId('borrow-cell-free-JB')).toHaveTextContent('50');
    expect(within(row).getByTestId('borrow-cell-committed-JB')).toHaveTextContent('50');
  });

  it('names a donor location by its code and a donor project by its reference', () => {
    renderDialog();

    expect(screen.getByText('HQ')).toBeInTheDocument();
    expect(screen.getByText('PRJ-0052 Seri Emas Phase 2')).toBeInTheDocument();
    expect(screen.getByText('Held at JB')).toBeInTheDocument();
  });

  it('shows what meeting this line leaves each donor with, before anything is typed', () => {
    renderDialog();

    fireEvent.change(screen.getByLabelText('Quantity'), { target: { value: '' } });

    // The server's own `available_after_need`, not availability: the column answers "if this
    // line takes what it still has to cover", which is the question the ranking answered.
    expect(screen.getByTestId('borrow-cell-after-HQ')).toHaveTextContent('60');
    expect(screen.getByTestId('borrow-cell-after-JB')).toHaveTextContent('-10');
  });

  it("keeps the server's order and flags the one donor it recommends", () => {
    renderDialog();

    const rows = within(screen.getByTestId('borrow-donor-table')).getAllByRole('row');
    // Header row first, then the donors in the order the server ranked them.
    expect(rows[1]).toHaveAttribute('data-testid', 'borrow-donor-HQ');
    expect(rows[2]).toHaveAttribute('data-testid', 'borrow-donor-JB');
    expect(within(rows[1]).getByText('Recommended')).toBeInTheDocument();
    expect(within(rows[2]).queryByText('Recommended')).not.toBeInTheDocument();
  });

  it('shows what each donor is left with once the typed quantity is taken', () => {
    renderDialog();

    fireEvent.change(screen.getByLabelText('Quantity'), { target: { value: '20' } });

    expect(screen.getByTestId('borrow-cell-after-HQ')).toHaveTextContent('60');
    expect(screen.getByTestId('borrow-cell-after-JB')).toHaveTextContent('-10');
  });

  it('states the impact of the typed quantity on the chosen donor, and updates with it', () => {
    renderDialog();

    fireEvent.change(screen.getByLabelText('Quantity'), { target: { value: '20' } });
    expect(screen.getByTestId('borrow-impact')).toHaveTextContent(
      'After borrowing 20: available 60, free 60',
    );

    fireEvent.change(screen.getByLabelText('Quantity'), { target: { value: '30' } });
    expect(screen.getByTestId('borrow-impact')).toHaveTextContent(
      'After borrowing 30: available 50, free 50',
    );
  });

  it('says a donor is left short, and that purchasing will be told (PLAN 13.11)', () => {
    renderDialog();

    const project = screen.getByTestId('borrow-donor-JB');
    fireEvent.click(within(project).getByRole('radio'));
    fireEvent.change(screen.getByLabelText('Quantity'), { target: { value: '30' } });

    const impact = screen.getByTestId('borrow-impact');
    expect(impact).toHaveTextContent('JB goes short by 20');
    expect(impact).toHaveTextContent('an Order Inquiry will be raised for JB on confirm');
  });

  it('renders the impact section even before a quantity is typed', () => {
    renderDialog();

    fireEvent.change(screen.getByLabelText('Quantity'), { target: { value: '' } });

    expect(screen.getByTestId('borrow-impact')).toHaveTextContent('No quantity yet');
  });

  it('opens on the recommended donor with the quantity this line still needs', () => {
    renderDialog();

    // 20 is the residual the ranking was computed against, not the donor's whole 80 free:
    // defaulting to "take everything they have" is the rule this dialog stopped using.
    expect(screen.getByLabelText('Quantity')).toHaveValue(20);
  });

  it('falls back to what the donor has free when the server states no need', () => {
    renderDialog([{ ...OTHER_LOCATION, need_qty: null, available_after_need: null }]);

    expect(screen.getByLabelText('Quantity')).toHaveValue(80);
  });

  it('offers only what a donor actually has when the need is larger than that', () => {
    renderDialog([{ ...OTHER_PROJECT, need_qty: '400' }]);

    expect(screen.getByLabelText('Quantity')).toHaveValue(50);
  });

  it('adds nothing until a reason is typed', () => {
    renderDialog();

    const add = screen.getByRole('button', { name: 'Add the borrow' });
    expect(add).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/Reason/), { target: { value: '   ' } });
    expect(add).toBeDisabled();
    expect(onAdd).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText(/Reason/), {
      target: { value: 'HQ has no delivery booked before October.' },
    });
    expect(add).toBeEnabled();
  });

  it('adds nothing on a zero or negative quantity', () => {
    renderDialog();

    fireEvent.change(screen.getByLabelText(/Reason/), {
      target: { value: 'HQ has no delivery booked before October.' },
    });
    fireEvent.change(screen.getByLabelText('Quantity'), { target: { value: '0' } });
    expect(screen.getByRole('button', { name: 'Add the borrow' })).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Quantity'), { target: { value: '-5' } });
    expect(screen.getByRole('button', { name: 'Add the borrow' })).toBeDisabled();
  });

  it('hands back the chosen candidate, the quantity and the trimmed reason', () => {
    renderDialog();

    fireEvent.change(screen.getByLabelText('Quantity'), { target: { value: '40' } });
    fireEvent.change(screen.getByLabelText(/Reason/), {
      target: { value: '  HQ has no delivery booked before October.  ' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Add the borrow' }));

    expect(onAdd).toHaveBeenCalledWith(
      OTHER_LOCATION,
      '40',
      'HQ has no delivery booked before October.',
    );
    expect(onDone).toHaveBeenCalled();
  });

  it('switches to another donor and re-fills the quantity with what the line needs', () => {
    renderDialog();

    const project = screen.getByTestId('borrow-donor-JB');
    fireEvent.click(within(project).getByRole('radio'));

    expect(screen.getByLabelText('Quantity')).toHaveValue(20);

    fireEvent.change(screen.getByLabelText(/Reason/), {
      target: { value: 'Their hand-over is in December.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Add the borrow' }));

    expect(onAdd).toHaveBeenCalledWith(
      OTHER_PROJECT,
      '20',
      'Their hand-over is in December.',
    );
  });

  it('says "Not stated" rather than 0 for a figure the server did not answer', () => {
    renderDialog([{ ...OTHER_LOCATION, so_qty: null, available_qty: null }]);

    expect(screen.getByTestId('borrow-cell-so-HQ')).toHaveTextContent('Not stated');
    expect(screen.getByTestId('borrow-cell-after-HQ')).toHaveTextContent('Not stated');
  });

  it('closes on cancel without adding anything', () => {
    renderDialog();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(onDone).toHaveBeenCalled();
    expect(onAdd).not.toHaveBeenCalled();
  });

  it('uses a dialog rather than the browser confirm', () => {
    const nativeConfirm = vi.spyOn(window, 'confirm');

    renderDialog();
    fireEvent.change(screen.getByLabelText(/Reason/), { target: { value: 'Because.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add the borrow' }));

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(nativeConfirm).not.toHaveBeenCalled();
  });

  it('renders no UUID-looking id, though it addresses the donor by one', () => {
    const { container } = renderDialog();

    expect(container.textContent).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-/i);
    expect(screen.getByRole('dialog').textContent).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-/i);
  });
});
