import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { ReorderRunSummary } from '../types/reorder.types';
import { ReorderStatTiles } from './ReorderStatTiles';

const summary: ReorderRunSummary = {
  buy_count: 3,
  disposition_count: 2,
  exception_count: 1,
  total_cash_impact: 12500,
  recommendation_count: 5,
};

describe('ReorderStatTiles', () => {
  it('toggle-filters the grid when a count tile is clicked', () => {
    const onToggle = vi.fn();
    render(<ReorderStatTiles summary={summary} activeType="" onToggle={onToggle} />);

    fireEvent.click(screen.getByText('Buy recommendations'));
    expect(onToggle).toHaveBeenCalledWith('buy');

    fireEvent.click(screen.getByText('Dispositions'));
    expect(onToggle).toHaveBeenCalledWith('disposition');

    fireEvent.click(screen.getByText('No-supplier exceptions'));
    expect(onToggle).toHaveBeenCalledWith('exception');
  });

  it('marks the active tile as pressed (selected state)', () => {
    render(<ReorderStatTiles summary={summary} activeType="buy" onToggle={() => {}} />);
    const buyTile = screen.getByText('Buy recommendations').closest('[role="button"]');
    expect(buyTile).toHaveAttribute('aria-pressed', 'true');
    const dispTile = screen.getByText('Dispositions').closest('[role="button"]');
    expect(dispTile).toHaveAttribute('aria-pressed', 'false');
  });

  it('keeps the total-cash-impact tile non-interactive (only the 3 counts toggle)', () => {
    render(<ReorderStatTiles summary={summary} activeType="" onToggle={() => {}} />);
    // exactly the three count tiles are buttons; cash tile is not
    expect(screen.getAllByRole('button')).toHaveLength(3);
    const cashTile = screen.getByText('Total cash impact').closest('[role="button"]');
    expect(cashTile).toBeNull();
  });
});
