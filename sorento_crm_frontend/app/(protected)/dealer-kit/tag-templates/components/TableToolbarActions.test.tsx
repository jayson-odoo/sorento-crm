/**
 * SPEC-SHEET-PARITY-B2 v3 fix round, review N3: Merge is disabled when the picked cell has nothing to
 * its right, for the picked cell. Written test-FIRST.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { TableLayerProps } from '@/lib/dealer-kit/tag-template-types';
import { TableToolbarActions } from './TableToolbarActions';

const props: TableLayerProps = {
  kind: 'table',
  columns: [{ width_mm: 10 }, { width_mm: 10 }],
  rows: [{ height_mm: 5 }],
  cells: [[{ text: 'a' }, { text: 'b' }]],
};

describe('Merge with nothing to merge into (review N3)', () => {
  it('disabled on the last column', () => {
    render(<TableToolbarActions props={props} cell={{ row: 0, col: 1 }} onChange={vi.fn()} />);
    expect(screen.getByRole('button', { name: /^merge/i })).toBeDisabled();
  });

  it('enabled when there is a cell to the right', () => {
    render(<TableToolbarActions props={props} cell={{ row: 0, col: 0 }} onChange={vi.fn()} />);
    expect(screen.getByRole('button', { name: /^merge/i })).toBeEnabled();
  });

  it('keeps the names the toolbar row tests use, compact enough for 1280 (review F2)', () => {
    render(<TableToolbarActions props={props} cell={null} onChange={vi.fn()} onInsertField={vi.fn()} />);
    for (const name of [/(\+ ?|add )row/i, /(\+ ?|add )column/i, /^merge/i, /^header row$/i, /^insert field$/i]) {
      const button = screen.getByRole('button', { name });
      // Icon buttons (the name is a hidden label), so the row fits 1280 with the group showing.
      expect(button.className, String(name)).toMatch(/\bw-8\b/);
    }
  });
});
