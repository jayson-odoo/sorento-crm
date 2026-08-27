/**
 * SCM M8 - ReorderStatTiles, now ONLY the decision-progress tile + the two cash tiles
 * (direct user feedback, 2026-08-12: "I don't really need these" about the secondary row -
 * Needs a level, Stock allocation, Order summary, Plan exceptions, PO worklist). Those five
 * are gone from this component entirely; Needs a level / Stock allocation are reachable as a
 * Status filter on the one grid, and Order summary / Plan exceptions / PO worklist moved to
 * a quiet toolbar link.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ReorderStatTiles } from './ReorderStatTiles';

function renderTiles(over: Partial<React.ComponentProps<typeof ReorderStatTiles>> = {}) {
  const onToggleUndecidedFilter = vi.fn();
  render(
    <ReorderStatTiles
      decided={0}
      total={0}
      cashCommitted={0}
      cashTotal={125000}
      onToggleUndecidedFilter={onToggleUndecidedFilter}
      {...over}
    />,
  );
  return { onToggleUndecidedFilter };
}

describe('ReorderStatTiles - only three tiles render', () => {
  it('never renders a Buy or Covered by stock tile', () => {
    renderTiles();
    expect(screen.queryByText('Buy')).not.toBeInTheDocument();
    expect(screen.queryByText('Covered by stock')).not.toBeInTheDocument();
  });

  it('never renders the removed secondary-row tiles', () => {
    renderTiles();
    expect(screen.queryByText('Needs a level')).not.toBeInTheDocument();
    expect(screen.queryByText('Stock allocation')).not.toBeInTheDocument();
    expect(screen.queryByText('Order summary')).not.toBeInTheDocument();
    expect(screen.queryByText('Plan exceptions')).not.toBeInTheDocument();
    expect(screen.queryByText('PO worklist')).not.toBeInTheDocument();
  });
});

describe('ReorderStatTiles - the decision-progress tile (0 / partial / all)', () => {
  it('reads "0 of N made" when nothing has been decided yet', () => {
    renderTiles({ decided: 0, total: 38 });
    expect(screen.getByText('0 of 38 made')).toBeInTheDocument();
    expect(screen.getByText('38 left to decide')).toBeInTheDocument();
  });

  it('reads the partial count while some lines are still undecided', () => {
    renderTiles({ decided: 12, total: 38 });
    expect(screen.getByText('12 of 38 made')).toBeInTheDocument();
    expect(screen.getByText('26 left to decide')).toBeInTheDocument();
  });

  it('shows a quiet completion state once every line is decided', () => {
    renderTiles({ decided: 38, total: 38 });
    expect(screen.getByText('38 of 38 made')).toBeInTheDocument();
    expect(screen.getByText('All 38 decided')).toBeInTheDocument();
  });

  it('toggles the undecided filter when clicked', () => {
    const { onToggleUndecidedFilter } = renderTiles({ decided: 12, total: 38 });
    fireEvent.click(screen.getByText('Decisions'));
    expect(onToggleUndecidedFilter).toHaveBeenCalled();
  });

  it('rings the tile when the undecided filter is active', () => {
    renderTiles({ decided: 12, total: 38, undecidedFilterActive: true });
    expect(screen.getByTitle('Show only lines still to decide')).toHaveAttribute(
      'aria-pressed', 'true',
    );
  });
});

describe('ReorderStatTiles - cash splits into committed vs if-all-accepted', () => {
  it('shows both cash figures with their own labels', () => {
    renderTiles({ cashCommitted: 4500, cashTotal: 125000 });
    expect(screen.getByText('Cash committed so far')).toBeInTheDocument();
    expect(screen.getByText('RM 4,500')).toBeInTheDocument();
    expect(screen.getByText('Cash if all accepted')).toBeInTheDocument();
    expect(screen.getByText('RM 125,000')).toBeInTheDocument();
  });

  it('renders the cash tiles as non-interactive', () => {
    renderTiles();
    expect(screen.queryByTitle('Show Cash committed so far recommendations')).not.toBeInTheDocument();
    expect(screen.queryByTitle('Show Cash if all accepted recommendations')).not.toBeInTheDocument();
  });
});

describe('ReorderStatTiles - the To confirm tile (AC-D4)', () => {
  /** Order inquiry rows purchasing has not confirmed yet. The plan credits confirmed rows
   *  only, so this tile is the plan's one sight of the work it cannot count itself. */
  it('states the count and leads to that list, already narrowed', () => {
    renderTiles({ awaitingRows: 7 });
    expect(screen.getByText('To confirm')).toBeInTheDocument();
    expect(screen.getByText('7')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /To confirm/ })).toHaveAttribute(
      'href', '/project-sales/order-inquiries?ack=to_confirm',
    );
  });

  it('stays away on a day with nothing waiting', () => {
    renderTiles({ awaitingRows: 0 });
    expect(screen.queryByText('To confirm')).not.toBeInTheDocument();
  });

  it('stays away when the summary says nothing about it', () => {
    renderTiles();
    expect(screen.queryByText('To confirm')).not.toBeInTheDocument();
  });
});
