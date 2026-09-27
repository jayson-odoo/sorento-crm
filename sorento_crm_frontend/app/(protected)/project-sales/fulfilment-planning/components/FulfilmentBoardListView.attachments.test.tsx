/**
 * The board's paperclip column (#1312, PLAN-oi-line-attachments-27sep.md, AC-U1/AC-U2):
 * every row carrying a core line id gets its own attachments button in the Verdict cell,
 * after `BoardVerdictActions`, and the count comes from ONE lookup call per grid, never
 * one per row.
 *
 * `SoLineAttachmentsButton` itself is mocked (its own contract is
 * `SoLineAttachmentsButton.test.tsx`'s job) - what this file pins is that the BOARD wires
 * a core `line_id` into it, one per contributing line, and reads every visible line's
 * attachments through a single batched lookup call.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { BoardContribution, BoardDraft } from '../../_shared/types/fulfilmentPlanning.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const lookupFn = vi.fn().mockReturnValue({ data: {}, isLoading: false });
vi.mock('@/app/(protected)/project-sales/_shared/hooks/useSoLineAttachments', () => ({
  useSoLineAttachmentLookup: (lineIds: string[]) => lookupFn(lineIds),
}));

vi.mock('@/app/(protected)/project-sales/_shared/components/SoLineAttachmentsButton', () => ({
  SoLineAttachmentsButton: ({ lineId, label }: { lineId: string; label: string }) => (
    <span data-testid={`attachments-button-${lineId}`}>{label}</span>
  ),
}));

import { FulfilmentBoardListView } from './FulfilmentBoardListView';

function contribution(overrides: Partial<BoardContribution> = {}): BoardContribution {
  return {
    key: 'so-1:line-10',
    sales_order_id: 'so-1',
    line_id: 'core-line-10',
    product_id: 'prod-1',
    so_number: 'SO397450',
    customer_name: 'Tuju Residences Sdn Bhd',
    agent_code: 'JEREMY',
    agent_label: 'Jeremy Lee',
    project_label: 'Tuju Residences',
    line_no: 10,
    item_code: 'B2155-NL-BLUE',
    qty: '43',
    qty_outstanding: '43',
    required_date: '2026-09-04',
    unplannable: false,
    rank_score: 0.82,
    rank_factors: [],
    sources: [{ kind: 'buy', qty: '43', reason: 'Nothing free at any location.' }],
    trail: [],
    item_flags: null,
    contested: false,
    covered: false,
    decision: null,
    ...overrides,
  };
}

function renderView(contributions: BoardContribution[], draft: BoardDraft = {}) {
  return render(
    <FulfilmentBoardListView
      contributions={contributions}
      draft={draft}
      onDecide={vi.fn()}
      onDecideMany={vi.fn()}
      onDecideBatch={vi.fn()}
    />,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  lookupFn.mockReturnValue({ data: {}, isLoading: false });
});

describe('FulfilmentBoardListView: attachments paperclip (AC-U1/AC-U2)', () => {
  it('renders a paperclip per row carrying a core line id', async () => {
    renderView([
      contribution({ key: 'so-1:line-10', line_id: 'core-line-10' }),
      contribution({
        key: 'so-2:line-20',
        sales_order_id: 'so-2',
        line_id: 'core-line-20',
        so_number: 'SO397451',
        line_no: 20,
      }),
    ]);

    expect(await screen.findByTestId('attachments-button-core-line-10')).toBeInTheDocument();
    expect(screen.getByTestId('attachments-button-core-line-20')).toBeInTheDocument();
  });

  it('renders no paperclip for a row with no core line id', async () => {
    renderView([contribution({ line_id: null })]);

    await screen.findByText('SO397450');
    expect(screen.queryByTestId(/^attachments-button-/)).not.toBeInTheDocument();
  });

  it('looks up every visible line in ONE call, not one call per row', async () => {
    renderView([
      contribution({ key: 'so-1:line-10', line_id: 'core-line-10' }),
      contribution({
        key: 'so-2:line-20',
        sales_order_id: 'so-2',
        line_id: 'core-line-20',
        so_number: 'SO397451',
        line_no: 20,
      }),
    ]);

    await screen.findByTestId('attachments-button-core-line-10');

    expect(lookupFn).toHaveBeenCalledTimes(1);
    expect(lookupFn).toHaveBeenCalledWith(
      expect.arrayContaining(['core-line-10', 'core-line-20']),
    );
  });
});
