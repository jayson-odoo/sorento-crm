/**
 * CONFIRM-PREVIEW-STALE (owner, 2 Nov 2026): a line whose saved decision differs from what
 * AutoCount's pending change suggests is FLAGGED on the Review split page with Keep / Take
 * suggestion. A warning, never a refusal: Next stays on.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../_shared/services/lineSplitService', () => ({
  getLineSplits: vi.fn().mockResolvedValue(null),
  saveLineSplits: vi.fn(),
}));

import { ConfirmGuideDialog, type ConfirmGuidePage } from './ConfirmGuideDialog';

const page = (moved: ConfirmGuidePage['covered'][number]['moved']): ConfirmGuidePage => ({
  psoId: null,
  salesOrderId: 'so-1',
  soNumber: 'SO000001',
  covered: [
    {
      lineId: null,
      key: 'k-10',
      lineNo: 10,
      itemCode: 'ZZT-ITEM-1',
      location: 'BRW-BB',
      qty: 3,
      date: '2026-11-02',
      savedRemark: 'ORDER BACK',
      ownRemark: null,
      remarkEditable: true,
      moved,
    },
  ],
});

function renderGuide(pages: ConfirmGuidePage[], onTakeSuggestion = vi.fn(), refreshing = false) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(
    <QueryClientProvider client={client}>
      <ConfirmGuideDialog
        pages={pages}
        runConfirm={vi.fn().mockResolvedValue(true)}
        saveRemarks={vi.fn().mockResolvedValue(undefined)}
        onTakeSuggestion={onTakeSuggestion}
        refreshing={refreshing}
        onClose={vi.fn()}
      />
    </QueryClientProvider>,
  );
  return onTakeSuggestion;
}

describe('CONFIRM-PREVIEW-STALE: suggestion moved warning', () => {
  it('flags the line with the suggestion and what is kept, and Next stays on', () => {
    renderGuide([page({ suggestion: 'Buy 3', kept: 'Borrow other location 3 from BRW' })]);
    const flag = screen.getByTestId('confirm-guide-moved');
    expect(flag).toHaveTextContent(
      'Line 10 ZZT-ITEM-1: AutoCount moved this line: suggestion Buy 3, you keep Borrow other location 3 from BRW',
    );
    expect(screen.getByTestId('confirm-guide-next')).toBeEnabled();
  });

  it('Keep hides the warning and changes nothing', () => {
    const take = renderGuide([page({ suggestion: 'Buy 3', kept: 'Borrow 3' })]);
    fireEvent.click(screen.getByRole('button', { name: 'Keep' }));
    expect(screen.queryByTestId('confirm-guide-moved')).not.toBeInTheDocument();
    expect(take).not.toHaveBeenCalled();
  });

  it('Take suggestion hands the line key to the board', () => {
    const take = renderGuide([page({ suggestion: 'Buy 3', kept: 'Borrow 3' })]);
    fireEvent.click(screen.getByRole('button', { name: 'Take suggestion' }));
    expect(take).toHaveBeenCalledWith('k-10');
  });

  it('no warning on a line that reads as the suggestion', () => {
    renderGuide([page(null)]);
    expect(screen.queryByTestId('confirm-guide-moved')).not.toBeInTheDocument();
  });

  it('while the board re-reads, the page waits: no rows, Next off', () => {
    renderGuide([page({ suggestion: 'Buy 3', kept: 'Borrow 3' })], vi.fn(), true);
    expect(screen.queryByTestId('confirm-guide-moved')).not.toBeInTheDocument();
    expect(screen.getByTestId('confirm-guide-next')).toBeDisabled();
  });
});
