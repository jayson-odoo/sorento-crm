/**
 * OI-WHOLE-SO-CANCEL F2 (crew ruling: mirror Suggested), red: in the board's list view the
 * Decided cell of a book-cancelled line whose cancel is SAVED (an approval with an empty
 * composition) reads "Cancel line", the same label as the Suggested column. Before saving it
 * keeps today's text; a normal saved Buy still prints its composition. Harness from
 * `FulfilmentBoardListView.so-cancel-line.test.tsx`.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type {
  BoardContribution,
  BoardDraft,
} from '../../_shared/types/fulfilmentPlanning.types';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

import { FulfilmentBoardListView } from './FulfilmentBoardListView';

const KEY = 'so-1:line-10';

function row(over: Record<string, unknown> = {}): BoardContribution {
  return {
    key: KEY,
    sales_order_id: 'so-1',
    line_id: 'core-line-10',
    project_line_id: 'pl-10',
    product_id: 'prod-1',
    so_number: 'SO900001',
    customer_name: 'ZZT Customer Sdn Bhd',
    line_no: 10,
    so_line_no: 10,
    item_code: 'CB110',
    qty: '0',
    qty_outstanding: '0',
    required_date: '2026-09-04',
    unplannable: false,
    rank_score: 0,
    rank_factors: [],
    sources: [],
    trail: [],
    item_flags: null,
    contested: false,
    covered: false,
    decision: null,
    cancelled: true,
    cancelled_at: null,
    pending_change_batch_id: 'b1',
    ...over,
  } as unknown as BoardContribution;
}

const SAVED_CANCEL = {
  verdict: 'approved',
  reserve: [],
  borrow: [],
  timely_spo_qty: '0',
  buy_qty: '0',
  order_back: false,
} as unknown as BoardDraft[string];

const PRE_MARK = {
  [KEY]: { verdict: 'approved', preMarked: true },
} as unknown as BoardDraft;

function decidedCell(contribution: BoardContribution, draft: BoardDraft): HTMLElement {
  render(
    <FulfilmentBoardListView
      contributions={[contribution]}
      draft={draft}
      onDecide={vi.fn()}
      onDecideMany={vi.fn(async () => ({ saved: 0, failed: 0 }))}
      onDecideBatch={vi.fn(async () => ({ savedKeys: [], failed: [] }))}
    />,
  );
  const tr = screen.getByText('SO900001').closest('tr') as HTMLElement;
  const headers = screen.getAllByRole('columnheader').map((h) => h.textContent?.trim());
  const index = headers.findIndex((name) => name === 'Decided');
  expect(index, 'the list has a Decided column').toBeGreaterThanOrEqual(0);
  return within(tr).getAllByRole('cell')[index] as HTMLElement;
}

describe('FulfilmentBoardListView: the Decided cell of a book-cancelled line (F2)', () => {
  it('reads "Cancel line" once the cancel is saved (approved, empty composition)', () => {
    expect(decidedCell(row(), { [KEY]: SAVED_CANCEL })).toHaveTextContent('Cancel line');
  });

  it('reads "Cancel line" for a server-saved approval (a non-pre-marked draft)', () => {
    expect(decidedCell(row(), { [KEY]: { verdict: 'approved' } as BoardDraft[string] })).toHaveTextContent(
      'Cancel line',
    );
  });

  it('stays "Not decided" while the draft is only the board-load pre-mark', () => {
    const cell = decidedCell(row(), PRE_MARK);
    expect(cell).toHaveTextContent('Not decided');
    expect(cell).not.toHaveTextContent('Cancel line');
  });

  it('stays "Not decided" for an OLD active decision with an empty composition and only the pre-mark', () => {
    const covered = row({
      covered: true,
      decision: { id: 'd-1', revision_no: 3, reserve: [], borrow: [], buy_qty: '0', timely_spo_qty: '0' },
    });
    const cell = decidedCell(covered, PRE_MARK);
    expect(cell).not.toHaveTextContent('Cancel line');
    expect(cell).toHaveTextContent('Not decided');
  });

  it('keeps today\'s text while the cancel is unsaved', () => {
    const cell = decidedCell(row(), {});
    expect(cell).toHaveTextContent('Not decided');
    expect(cell).not.toHaveTextContent('Cancel line');
  });

  it('guard: a normal saved Buy still prints its composition', () => {
    const normal = row({ cancelled: false, pending_change_batch_id: null, qty: '10', qty_outstanding: '10' });
    const buy = { ...SAVED_CANCEL, buy_qty: '10', buy_reason: 'No stock' } as unknown as BoardDraft[string];
    const cell = decidedCell(normal, { [KEY]: buy });
    expect(cell).toHaveTextContent('Buy 10');
    expect(cell).not.toHaveTextContent('Cancel line');
  });
});

describe('FulfilmentBoardListView: book-cancelled rows are selectable (OI-WHOLE-SO-CANCEL)', () => {
  function renderRows() {
    const rows = [
      row({ key: 'so-1:line-10', so_number: 'SO900001', line_no: 10, so_line_no: 10 }),
      row({ key: 'so-2:line-20', so_number: 'SO900002', line_no: 20, so_line_no: 20 }),
    ];
    render(
      <FulfilmentBoardListView
        contributions={rows}
        draft={{}}
        onDecide={vi.fn()}
        onDecideMany={vi.fn(async () => ({ saved: 0, failed: 0 }))}
        onDecideBatch={vi.fn(async () => ({ savedKeys: [], failed: [] }))}
      />,
    );
  }

  it('each row checkbox is present and enabled', async () => {
    renderRows();
    await screen.findByText('SO900001');
    const boxes = screen.getAllByRole('checkbox').filter((b) => /^Select SO/.test(b.getAttribute('aria-label') ?? ''));
    expect(boxes).toHaveLength(2);
    for (const box of boxes) expect(box).toBeEnabled();
  });

  it('select-all ticks every book-cancelled row and enables Decide', async () => {
    renderRows();
    await screen.findByText('SO900001');
    fireEvent.click(screen.getByRole('checkbox', { name: 'Select all rows' }));
    await waitFor(() => expect(screen.getByTestId('board-decide-button')).toBeEnabled());
    const boxes = screen.getAllByRole('checkbox').filter((b) => /^Select SO/.test(b.getAttribute('aria-label') ?? ''));
    for (const box of boxes) expect(box).toBeChecked();
  });
});
