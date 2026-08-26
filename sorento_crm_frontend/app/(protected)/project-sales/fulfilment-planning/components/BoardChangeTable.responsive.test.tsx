/**
 * The board's Was / Now table at 375px (`PLAN-scm-cs-planning-uat.md` part 3, AC-P3-2 / AC-P3-3).
 *
 * Two things the plan's "structure, not words" ruling and the mobile design mandate both ask
 * for on this one component:
 *
 * 1. The table never overflows its cell. `BoardChangeTable` sits inside a ~150px board cell
 *    on a phone as much as on a desktop, so its width has to come from the cell it is given,
 *    never from its own content - `w-full` + `table-fixed` on the table, percentage column
 *    widths, `truncate` on anything that can run long (the SO number, a decision sentence).
 *    jsdom does not lay out CSS, so this is a class-level check, not a measured one.
 * 2. The batch's own reaction vocabulary - Keep / Release / Replan / Reduce / Retire - never
 *    reaches the screen at any width, because a planner reads supply in board words only
 *    (`boardChangeAnnotations.ts` module docstring, rule 1).
 */
import React from 'react';
import { render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { BoardChangeTable } from './BoardChangeTable';
import type { BoardChangeAnnotation } from '../../_shared/lib/boardChangeAnnotations';

function annotation(overrides: Partial<BoardChangeAnnotation> = {}): BoardChangeAnnotation {
  return {
    rowId: 'pcr-381895-1',
    soNumber: 'SO381895',
    lineNo: 1,
    itemCode: 'SRTWCX7405-RL-S-PJ',
    kind: 'advanced',
    closed: false,
    was: { qty: '10', date: '2026-08-25', decision: 'Buy 10' },
    now: {
      qty: '25',
      date: '2026-08-19',
      decision: 'Use shared stock 5 from BRW, 10 from WH3 . Borrow other location 10 from WH3-NTC',
    },
    movedTransfer: null,
    projectLineId: 'pl-381895-1',
    ...overrides,
  };
}

const ORIGINAL_WIDTH = window.innerWidth;

function setViewport(width: number) {
  Object.defineProperty(window, 'innerWidth', { value: width, configurable: true, writable: true });
  window.dispatchEvent(new Event('resize'));
}

beforeEach(() => {
  setViewport(375);
});

afterEach(() => {
  setViewport(ORIGINAL_WIDTH);
  vi.restoreAllMocks();
});

describe('the Was / Now table at 375px', () => {
  it('draws from a full-width, table-fixed container rather than a fixed pixel width', () => {
    render(<BoardChangeTable annotation={annotation()} />);
    const container = screen.getByTestId('board-change-pcr-381895-1');

    // The cell it is drawn inside sizes it; it must never size itself. `table-fixed` +
    // `w-full` is what makes the column percentages (below) actually hold the layout,
    // rather than the browser widening the table to fit its longest cell's content.
    expect(container.className).toMatch(/\bw-full\b/);
    expect(container.className).not.toMatch(/\bw-\[\d/);

    const table = container.querySelector('table');
    expect(table).not.toBeNull();
    expect(table?.className).toMatch(/\btable-fixed\b/);
    expect(table?.className).toMatch(/\bw-full\b/);
  });

  it('gives every column a percentage width, none of them a fixed pixel one', () => {
    render(<BoardChangeTable annotation={annotation()} />);
    const table = screen.getByTestId('board-change-pcr-381895-1').querySelector('table');
    const headers = Array.from(table?.querySelectorAll('thead th') ?? []);
    expect(headers).toHaveLength(3);
    for (const header of headers) {
      expect(header.className).toMatch(/\bw-\[\d+%\]/);
      expect(header.className).not.toMatch(/\bw-\[\d+px\]/);
    }
  });

  it('truncates the long text a decision sentence and an SO number can carry, rather than widening the cell', () => {
    render(
      <BoardChangeTable
        annotation={annotation({
          soNumber: 'SO381895-A-VERY-LONG-DOCUMENT-NUMBER-THAT-SHOULD-NEVER-WIDEN-THE-CELL',
        })}
      />,
    );
    const container = screen.getByTestId('board-change-pcr-381895-1');
    const soNumberEl = within(container).getByTitle('SO381895-A-VERY-LONG-DOCUMENT-NUMBER-THAT-SHOULD-NEVER-WIDEN-THE-CELL');
    expect(soNumberEl.className).toMatch(/\btruncate\b/);

    const decisionCell = screen.getByTestId('change-now-decision');
    expect(decisionCell.className).toMatch(/\btruncate\b/);
  });

  it('shrinks to a 10px compact scale inside the board cell, never wrapping into a taller cell', () => {
    render(<BoardChangeTable annotation={annotation()} compact />);
    const container = screen.getByTestId('board-change-pcr-381895-1');
    expect(container.className).toMatch(/text-\[10px\]/);
  });

  it('never renders the batch internal reaction words, at 375px or otherwise', () => {
    render(<BoardChangeTable annotation={annotation()} />);
    const printed = screen.getByTestId('board-change-pcr-381895-1').textContent ?? '';
    for (const verb of ['Keep', 'Release', 'Replan', 'Reduce', 'Retire']) {
      expect(printed).not.toContain(verb);
    }
  });
});
