/**
 * SCM M8 - DispositionResultsGrid (M8-F18). The Stock allocation view shows ONLY
 * actionable rows (Discontinue / Promote) in the main table; FYI "hold" rows are
 * demoted (not dropped) into a muted, collapsed "No action needed (N)" section, and
 * a zero-actionable plan shows a clean empty state with the hold section still below.
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DispositionResultsGrid } from './DispositionResultsGrid';
import type { M8DispositionRow } from '../lib/planRow';

function drow(over: Partial<M8DispositionRow> & Pick<M8DispositionRow, 'id' | 'action'>): M8DispositionRow {
  return {
    sku: `SKU-${over.id}`,
    product_name: `Product ${over.id}`,
    qty: 100,
    warehouse_code: 'WH-KL',
    warehouse_name: 'Kuala Lumpur DC',
    days_cover: 900,
    reason: 'overstock: 961 days of cover exceeds the ceiling',
    ...over,
  };
}

describe('DispositionResultsGrid (M8-F18)', () => {
  it('shows actionable rows in the main list and hides hold rows behind the collapsed section', () => {
    render(
      <DispositionResultsGrid
        rows={[
          drow({ id: 'kill', action: 'discontinue', sku: 'DEAD-1' }),
          drow({ id: 'h1', action: 'hold', sku: 'HOLD-1' }),
          drow({ id: 'h2', action: 'hold', sku: 'HOLD-2' }),
        ]}
      />,
    );
    // actionable is visible in the main table
    expect(screen.getByText('DEAD-1')).toBeInTheDocument();
    // hold rows are demoted + collapsed by default
    expect(screen.queryByText('HOLD-1')).not.toBeInTheDocument();
    expect(screen.getByText('No action needed (2)')).toBeInTheDocument();
  });

  it('expands the hold section on click, revealing the hold rows (not deleted)', () => {
    render(
      <DispositionResultsGrid
        rows={[
          drow({ id: 'kill', action: 'discontinue', sku: 'DEAD-1' }),
          drow({ id: 'h1', action: 'hold', sku: 'HOLD-1' }),
        ]}
      />,
    );
    fireEvent.click(screen.getByText('No action needed (1)'));
    expect(screen.getByText('HOLD-1')).toBeInTheDocument();
  });

  it('shows a clean empty state when there is nothing actionable, hold section still below', () => {
    render(
      <DispositionResultsGrid
        rows={[
          drow({ id: 'h1', action: 'hold', sku: 'HOLD-1' }),
          drow({ id: 'h2', action: 'hold', sku: 'HOLD-2' }),
        ]}
      />,
    );
    expect(screen.getByText('No stock-allocation actions needed today')).toBeInTheDocument();
    expect(screen.getByText('No action needed (2)')).toBeInTheDocument();
  });
});
