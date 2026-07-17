/**
 * SCM M8 — ReorderStatTiles (M8-C0 / M8-C12). Exactly THREE summary cards — Buy,
 * Stock allocation, Cash impact — no Today's-plan / Stock-warning / Within / Over
 * cards. Buy + Stock allocation are clickable view filters (active ring); Cash
 * impact is a stat only. The old "Disposition" label is renamed to "Stock allocation".
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
  it('renders exactly the three summary cards with their counts', () => {
    renderTiles();
    expect(screen.getByText('Buy')).toBeInTheDocument();
    expect(screen.getByText('Stock allocation')).toBeInTheDocument();
    expect(screen.getByText('Cash impact')).toBeInTheDocument();
    expect(screen.getByText('7')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('RM 125,000')).toBeInTheDocument();
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
