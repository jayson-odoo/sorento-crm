/**
 * Stage 1C - adding a Borrow from a listed candidate (AC-B09, AC-B10).
 *
 * Borrowing takes exactly one approval: the CS actor who confirms the sales order, with
 * the donor's impact in front of them and a reason nobody can skip. So what is pinned here
 * is that the donor is named the way a person names it (warehouse code, project reference),
 * that the impact of taking the stock is stated before it is taken, and that Add stays shut
 * until a reason has actually been typed.
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

const OTHER_LOCATION: BorrowCandidate = {
  source: 'other_location',
  warehouse_code: 'HQ',
  warehouse_id: WH_HQ,
  free_qty: '80',
  donor_impact: { free_before: '80', free_after_full_borrow: '0', committed_qty: '140' },
};

const OTHER_PROJECT: BorrowCandidate = {
  source: 'other_project',
  warehouse_code: 'JB',
  warehouse_id: WH_JB,
  donor_project_ref: 'PRJ-0052 Seri Emas Phase 2',
  donor_project_id: DONOR_PROJECT,
  free_qty: '50',
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

  it('names a donor location by its code, with what is free and what is committed', () => {
    renderDialog();

    expect(screen.getByText('HQ')).toBeInTheDocument();
    expect(screen.getByText('80 free, 140 committed.')).toBeInTheDocument();
  });

  it('names a donor project by its reference, and says where the stock sits', () => {
    renderDialog();

    expect(screen.getByText('PRJ-0052 Seri Emas Phase 2')).toBeInTheDocument();
    expect(screen.getByText('Held at JB. 50 free, 50 committed.')).toBeInTheDocument();
  });

  it('states what taking all of it leaves the donor with, before it is taken (AC-B09)', () => {
    renderDialog();

    expect(screen.getByText('Borrowing all of it leaves 0 free.')).toBeInTheDocument();
    expect(screen.getByText('Borrowing all of it leaves 10 free.')).toBeInTheDocument();
  });

  it('opens on the first candidate with its free quantity already in the box', () => {
    renderDialog();

    expect(screen.getByLabelText('Quantity')).toHaveValue(80);
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

  it('switches to another donor and re-fills the quantity with what that one has free', () => {
    renderDialog();

    const project = screen
      .getByText('PRJ-0052 Seri Emas Phase 2')
      .closest('label') as HTMLElement;
    fireEvent.click(within(project).getByRole('radio'));

    expect(screen.getByLabelText('Quantity')).toHaveValue(50);

    fireEvent.change(screen.getByLabelText(/Reason/), {
      target: { value: 'Their hand-over is in December.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Add the borrow' }));

    expect(onAdd).toHaveBeenCalledWith(
      OTHER_PROJECT,
      '50',
      'Their hand-over is in December.',
    );
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
