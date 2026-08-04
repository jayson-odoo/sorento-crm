/**
 * SCM M8 - ReorderStatTiles (M8-C0 / M8-C12 + AC-B9 + AC-C2.1). SIX summary
 * cards - Buy, Stock allocation, Order summary, Cash impact, Plan exceptions,
 * PO worklist - and no Today's-plan / Stock-warning / Within / Over cards. Buy,
 * Stock allocation and Order summary are clickable view filters (active ring);
 * the other three are stats only. The old "Disposition" label is renamed to
 * "Stock allocation".
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ReorderStatTiles } from './ReorderStatTiles';

function renderTiles(over: Partial<React.ComponentProps<typeof ReorderStatTiles>> = {}) {
  const onSelectView = vi.fn();
  render(
    <ReorderStatTiles
      buyCount={7}
      dispositionCount={3}
      cashTotal={125000}
      activeView="buy"
      onSelectView={onSelectView}
      {...over}
    />,
  );
  return { onSelectView };
}

describe('ReorderStatTiles (M8-C0 / M8-C12)', () => {
  it('renders exactly the six summary cards with their counts', () => {
    renderTiles({ planExceptionCount: 4, poWorklistCount: 11, orderSummaryPendingCount: 2 });
    expect(screen.getByText('Buy')).toBeInTheDocument();
    expect(screen.getByText('Stock allocation')).toBeInTheDocument();
    expect(screen.getByText('Order summary')).toBeInTheDocument();
    expect(screen.getByText('Cash impact')).toBeInTheDocument();
    expect(screen.getByText('Plan exceptions')).toBeInTheDocument();
    expect(screen.getByText('PO worklist')).toBeInTheDocument();
    expect(screen.getByText('7')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('RM 125,000')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
    expect(screen.getByText('11')).toBeInTheDocument();
  });

  it('says what a zero order-summary count MEANS rather than leaving a bare 0', () => {
    renderTiles({ orderSummaryPendingCount: 0 });
    expect(screen.getByText('every planned item decided')).toBeInTheDocument();
  });

  it('admits it has not counted yet rather than showing a number it does not have', () => {
    // The count comes from the report query's cache, so before the report has been opened
    // there is genuinely nothing to state. This tile used to render a hard-coded mock
    // constant of 2 on the live page against a real book of 317 undecided rows.
    renderTiles({ orderSummaryPendingCount: null });
    expect(screen.getByText('open to count')).toBeInTheDocument();
    expect(screen.queryByText('waiting on a quantity')).not.toBeInTheDocument();
  });

  it('switches to the order-summary view when the Order summary card is clicked (AC-C2.1)', () => {
    const { onSelectView } = renderTiles({ activeView: 'buy' });
    fireEvent.click(screen.getByText('Order summary'));
    expect(onSelectView).toHaveBeenCalledWith('order_summary');
  });

  it('says what a zero plan-exception / PO-worklist count MEANS rather than leaving a bare 0', () => {
    renderTiles({ planExceptionCount: 0, poWorklistCount: 0 });
    expect(screen.getByText('nothing disagrees with placed supply')).toBeInTheDocument();
    expect(screen.getByText('nothing left to key')).toBeInTheDocument();
  });

  it('switches to plan exceptions when its card is clicked (S5, AC-D2)', () => {
    // It was a plain stat until S5 shipped the view, for the same reason the PO worklist
    // was: a card that switched to a view which did not exist is worse than a count.
    const { onSelectView } = renderTiles({ planExceptionCount: 4 });
    fireEvent.click(screen.getByText('Plan exceptions'));
    expect(onSelectView).toHaveBeenCalledWith('plan_exceptions');
  });

  it('opens the exceptions view even at "not computed", so the empty state is reachable', () => {
    // The queue is what somebody comes to this tile for. Gating the click on a count that
    // is only fetched once the view has been opened would make it unopenable.
    const { onSelectView } = renderTiles({ planExceptionCount: null });
    fireEvent.click(screen.getByText('Plan exceptions'));
    expect(onSelectView).toHaveBeenCalledWith('plan_exceptions');
  });

  it('switches to the PO worklist when its card is clicked (S4, AC-E2.1)', () => {
    // It was a stat until S4 shipped the view. A card that switched to a view which did
    // not exist would have been worse than a plain count, which is why it waited.
    const { onSelectView } = renderTiles({ poWorklistCount: 11 });
    fireEvent.click(screen.getByText('PO worklist'));
    expect(onSelectView).toHaveBeenCalledWith('po_worklist');
  });

  it('shows the actionable disposition count on the Stock allocation card, never a hold sub-label', () => {
    renderTiles({ dispositionCount: 12 });
    // headline value is actionable-only; hold lines are not surfaced here at all
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.queryByText(/on hold/i)).not.toBeInTheDocument();
  });

  it('never renders the removed cards or the old "Disposition" label (M8-C12)', () => {
    renderTiles();
    expect(screen.queryByText('Disposition')).not.toBeInTheDocument();
    expect(screen.queryByText(/Stock warning/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Within budget/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Over budget/i)).not.toBeInTheDocument();
  });

  it('switches to the buy view when the Buy card is clicked', () => {
    const { onSelectView } = renderTiles({ activeView: 'disposition' });
    fireEvent.click(screen.getByText('Buy'));
    expect(onSelectView).toHaveBeenCalledWith('buy');
  });

  it('switches to the disposition view when the Stock allocation card is clicked', () => {
    const { onSelectView } = renderTiles({ activeView: 'buy' });
    fireEvent.click(screen.getByText('Stock allocation'));
    expect(onSelectView).toHaveBeenCalledWith('disposition');
  });

  it('marks the active card with aria-pressed and leaves Cash impact non-interactive', () => {
    renderTiles({ activeView: 'buy' });
    const buyTile = screen.getByTitle('Show Buy recommendations');
    expect(buyTile).toHaveAttribute('aria-pressed', 'true');
    // Cash impact is a stat, not a clickable filter.
    expect(screen.queryByTitle('Show Cash impact recommendations')).not.toBeInTheDocument();
  });
});
