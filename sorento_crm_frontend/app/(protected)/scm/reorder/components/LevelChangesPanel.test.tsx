/**
 * The run-level list of AutoCount level changes (S13f, AC-S13f.3).
 *
 * The user reviews the plan, then carries the level changes into AutoCount by hand - so
 * the list holds ONLY the changes, named by product code, with a CSV to take along.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { LevelChangesPanel } from './LevelChangesPanel';
import type { LevelSuggestion } from '../lib/levelSuggestion';

const suggestion = (over: Partial<LevelSuggestion> = {}): LevelSuggestion => ({
  product_id: 'p1',
  warehouse_id: 'w1',
  product_code: 'SRT-100',
  product_name: 'Basin',
  warehouse_code: 'BRW',
  warehouse_name: 'Branch West',
  current_level: 20,
  current_source: 'autocount',
  suggested_level: 24,
  suggested_at: null,
  basis: {
    months: [], months_studied: 3, total_qty: 36, avg_monthly: 12, cover_months: 2,
    raw_level: 24, moq: null, order_multiple: null, trend: 'rising', no_movement: false,
  },
  ...over,
});

describe('LevelChangesPanel', () => {
  it('renders nothing when no level needs changing, because an empty ask is noise', () => {
    const { container } = render(
      <LevelChangesPanel suggestions={{ a: suggestion({ suggested_level: 20 }) }} />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it('counts the changes and lists them by code with both numbers', () => {
    render(
      <LevelChangesPanel
        suggestions={{
          a: suggestion(),
          b: suggestion({ product_id: 'p2', product_code: 'SRT-200', current_level: null, suggested_level: 8 }),
          c: suggestion({ product_id: 'p3', suggested_level: 20 }), // unchanged, stays out
        }}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /2 AutoCount levels to update/i }));

    expect(screen.getByText('SRT-100')).toBeInTheDocument();
    expect(screen.getByText('SRT-200')).toBeInTheDocument();
    expect(screen.queryAllByRole('row')).toHaveLength(3); // header + 2 changes
  });

  it('offers the list as a CSV named after the task', () => {
    const createObjectURL = vi.fn(() => 'blob:x');
    const revokeObjectURL = vi.fn();
    Object.assign(URL, { createObjectURL, revokeObjectURL });

    render(<LevelChangesPanel suggestions={{ a: suggestion() }} />);
    fireEvent.click(screen.getByRole('button', { name: /1 AutoCount level to update/i }));
    fireEvent.click(screen.getByRole('button', { name: /download csv/i }));

    expect(createObjectURL).toHaveBeenCalledTimes(1);
    const blob = createObjectURL.mock.calls[0][0] as Blob;
    expect(blob.type).toContain('text/csv');
  });
});
