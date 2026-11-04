/**
 * CONFIRM-PREVIEW-STALE (owner, 2 Nov 2026): the Review split page reads the split sheet again
 * as the guide opens. The "AutoCount moved this line" flag #2091 added here is gone
 * (NO-AC-MOVED-WARNING, owner 3 Nov 2026): its board-level guard lives in
 * `FulfilmentBoardPanel.confirmGuide.test.tsx`.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const getLineSplits = vi.fn().mockResolvedValue(null);
vi.mock('../../_shared/services/lineSplitService', () => ({
  getLineSplits: (...args: unknown[]) => getLineSplits(...args),
  saveLineSplits: vi.fn(),
}));

import { ConfirmGuideDialog, type ConfirmGuidePage } from './ConfirmGuideDialog';
import { LINE_SPLITS_KEY } from '../../_shared/hooks/useLineSplits';
import { wireLine } from '@/test-mocks/lineSplitSheetKit';

const page = (): ConfirmGuidePage => ({
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
    },
  ],
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
      ...page(),
      psoId: 'pso-1',
      covered: [{ ...page().covered[0], lineId: 'pl-10', savedRemark: null }],
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

