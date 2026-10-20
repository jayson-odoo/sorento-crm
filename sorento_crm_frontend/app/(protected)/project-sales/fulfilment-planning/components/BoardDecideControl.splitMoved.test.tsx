/**
 * OI-SPLIT-VIEW (UAC D2): "Split delivery..." leaves the Decide dropdown; it lives in the board
 * gear now (`FulfilmentBoardPanel.splitView.test.tsx`). Red until the item at
 * `BoardDecideControl.tsx:572-581` is removed.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { BoardDecideControl } from './BoardDecideControl';
import { LineSplitOpenerContext } from './lineSplitOpener';
import type { BoardContribution } from '../../_shared/types/fulfilmentPlanning.types';

vi.mock('@/lib/toast', () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), warning: vi.fn(), error: vi.fn() }),
}));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: () => <select aria-label="donor-or-location" />,
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

const ROW = {
  key: 'so-1:line-10',
  sales_order_id: 'so-1',
  so_number: 'SO397450',
  line_no: 10,
  item_code: 'B2155-NL-BLUE',
  qty: '40',
  unplannable: false,
  cancelled: false,
  rank_score: 1,
  rank_factors: [],
  sources: [{ kind: 'buy', qty: '40', reason: 'Nothing free at any location.' }],
  contested: false,
  covered: false,
  locations: [],
  borrow_candidates: [],
  project_line_id: 'pl-10',
} as unknown as BoardContribution;

describe('the Decide dropdown no longer offers Split delivery (D2)', () => {
  it('has no "Split delivery" item even where the board can open the split sheet', () => {
    const opener = { canOpen: () => true, open: vi.fn() };
    render(
      <LineSplitOpenerContext.Provider value={opener}>
        <BoardDecideControl
          contributions={[ROW]}
          selectedKeys={[ROW.key]}
          draft={{}}
          onSave={vi.fn() as never}
          onSaved={vi.fn()}
          onClear={vi.fn()}
          borrowFromOrderEnabled
        />
      </LineSplitOpenerContext.Provider>,
    );
    fireEvent.keyDown(screen.getByTestId('board-decide-button'), { key: 'Enter' });
    expect(screen.getAllByRole('menuitem').length).toBeGreaterThan(0);
    expect(screen.queryByRole('menuitem', { name: /Split delivery/ })).not.toBeInTheDocument();
  });
});
