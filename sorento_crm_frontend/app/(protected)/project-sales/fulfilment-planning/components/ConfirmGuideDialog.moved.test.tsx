/**
 * CONFIRM-PREVIEW-STALE (owner, 2 Nov 2026): a line whose saved decision differs from what
 * AutoCount's pending change suggests is FLAGGED on the Review split page with Keep / Take
 * suggestion. A warning, never a refusal: Next stays on.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const getLineSplits = vi.fn().mockResolvedValue(null);
vi.mock('../../_shared/services/lineSplitService', () => ({
  getLineSplits: (...args: unknown[]) => getLineSplits(...args),
  saveLineSplits: vi.fn(),
}));

import { ConfirmGuideDialog, type ConfirmGuidePage } from './ConfirmGuideDialog';
import { LINE_SPLITS_KEY } from '../../_shared/hooks/useLineSplits';
import { wireLine } from '@/test-mocks/lineSplitSheetKit';

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

describe('CONFIRM-PREVIEW-STALE: the split sheet is read again as the guide opens', () => {
  const readWith = (remark: string) => ({
    pso_id: 'pso-1',
    so_number: 'SO000001',
    so_date: '2026-09-03',
    customer: 'Test Customer',
    project: 'Test Project',
    confirmed_at: null,
    lines: [
      wireLine(10, 'ZZT-ITEM-1', 3, '2026-09-28', {
        line_id: 'pl-10',
        split_state: 'applied',
        remark_generated: remark,
        split_view: { status: 'confirmed' },
      } as never),
    ],
  });

  it('a cached sheet from before a Save is never printed: the page waits for the new read', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    // What the cache held from an earlier open, before the Save.
    client.setQueryData([LINE_SPLITS_KEY, 'pso-1'], readWith('OLDWORDS'));
    let answer: (value: unknown) => void = () => {};
    getLineSplits.mockImplementation(
      () =>
        new Promise((resolve) => {
          answer = resolve;
        }),
    );
    const fresh: ConfirmGuidePage = {
      ...page(null),
      psoId: 'pso-1',
      covered: [{ ...page(null).covered[0], lineId: 'pl-10', savedRemark: null }],
    };
    render(
      <QueryClientProvider client={client}>
        <ConfirmGuideDialog
          pages={[fresh]}
          runConfirm={vi.fn().mockResolvedValue(true)}
          saveRemarks={vi.fn().mockResolvedValue(undefined)}
          onClose={vi.fn()}
        />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(getLineSplits).toHaveBeenCalled());
    expect(screen.queryByText('OLDWORDS')).not.toBeInTheDocument();
    expect(screen.getByTestId('confirm-guide-next')).toBeDisabled();
    await act(async () => answer(readWith('NEWWORDS')));
    expect(await screen.findByText('NEWWORDS')).toBeInTheDocument();
    expect(screen.queryByText('OLDWORDS')).not.toBeInTheDocument();
  });
});

