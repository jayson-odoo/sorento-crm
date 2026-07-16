/**
 * SCM M4 Slice B — CashCopilotResults "staged decisions" confirm bar.
 *   - The confirm bar is ABSENT with no staged decisions.
 *   - It is PRESENT with the correct "(X accepted, Y adjusted)" summary once
 *     accepted/adjusted decisions are staged WITHOUT a draft PO.
 *   - It is ABSENT again once every staged decision carries a draft_po_id
 *     (i.e. it has been confirmed into a PO).
 *   - Clicking "Confirm decisions" opens the confirm dialog and confirming
 *     invokes the confirmDecisions mutation with [] (confirm all staged).
 *
 * The heavy presentational children (grids, budget panel, dialogs) are stubbed
 * so the assertions target THIS component's staging logic, and the data/decision
 * hooks are mocked via a hoisted state object the tests mutate per-case.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}

const hoisted = vi.hoisted(() => ({
  state: {
    data: [] as unknown[],
    isLoading: false,
    isError: false,
    byId: {} as Record<string, unknown>,
  },
  confirmMutate: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

vi.mock('../hooks/useReorderRun', () => ({
  useBuyRecommendationsForCash: () => ({
    data: hoisted.state.data,
    isLoading: hoisted.state.isLoading,
    isError: hoisted.state.isError,
  }),
}));
vi.mock('../hooks/useDecisions', () => ({
  useRecommendationDecisions: () => ({ byId: hoisted.state.byId }),
  useDecisionMutations: () => ({
    accept: { mutateAsync: vi.fn(), isPending: false },
    adjust: { mutateAsync: vi.fn(), isPending: false },
    reject: { mutateAsync: vi.fn(), isPending: false },
    bulkAccept: { mutateAsync: vi.fn(), isPending: false },
    bulkReject: { mutateAsync: vi.fn(), isPending: false },
    confirm: { mutateAsync: hoisted.confirmMutate, isPending: false },
  }),
}));

// Stub the presentational children — the confirm bar + ConfirmActionDialog are
// what these tests exercise; the grids/panels/dialogs are covered elsewhere.
vi.mock('./CashBudgetPanel', () => ({ CashBudgetPanel: () => <div data-testid="budget-panel" /> }));
vi.mock('./CashResultsGrid', () => ({ CashResultsGrid: () => <div data-testid="results-grid" /> }));
vi.mock('./AdjustRecommendationModal', () => ({ AdjustRecommendationModal: () => null }));
vi.mock('./RejectRecommendationDialog', () => ({ RejectRecommendationDialog: () => null }));
vi.mock('./BulkRejectDialog', () => ({ BulkRejectDialog: () => null }));
vi.mock('./ReorderExplanationDialog', () => ({ ReorderExplanationDialog: () => null }));
vi.mock('../../components/ConfirmActionDialog', () => ({
  ConfirmActionDialog: ({ open, title, confirmLabel, onConfirm }: any) =>
    open ? (
      <div role="dialog" aria-label={title}>
        <span>{title}</span>
        <button type="button" data-testid="dialog-confirm" onClick={onConfirm}>
          {confirmLabel}
        </button>
      </div>
    ) : null,
}));

import { CashCopilotResults } from './CashCopilotResults';
import type { RecDecision } from '../types/decisions.types';

function rec(id: string, over: Record<string, unknown> = {}) {
  return {
    id,
    type: 'buy',
    sku: `SKU-${id}`,
    cash_impact: 4200,
    order_qty: 100,
    rank: 1,
    rank_score: 0.8,
    days_to_stockout: 5,
    funding_status: 'funded',
    rank_factors: [],
    ...over,
  } as unknown;
}

function decision(id: string, over: Partial<RecDecision>): RecDecision {
  return {
    recommendation_id: id,
    status: 'accepted',
    override_qty: null,
    override_supplier_code: null,
    override_supplier_name: null,
    reason_text: null,
    draft_po_number: null,
    draft_po_id: null,
    ...over,
  };
}

beforeEach(() => {
  cleanup();
  hoisted.confirmMutate.mockReset();
  hoisted.confirmMutate.mockResolvedValue({ confirmed_count: 3, po_count: 2 });
  hoisted.state.data = [rec('a'), rec('b'), rec('c')];
  hoisted.state.isLoading = false;
  hoisted.state.isError = false;
  hoisted.state.byId = {};
});

describe('CashCopilotResults — staged-decisions confirm bar', () => {
  it('hides the confirm bar when nothing is staged', () => {
    hoisted.state.byId = {};
    render(<CashCopilotResults runId="run-1" enabled />);
    expect(screen.queryByRole('button', { name: /Confirm decisions/i })).toBeNull();
  });

  it('shows the bar with the accepted/adjusted breakdown for unconfirmed staged decisions', () => {
    hoisted.state.byId = {
      a: decision('a', { status: 'accepted' }),
      b: decision('b', { status: 'adjusted', override_qty: 250 }),
      c: decision('c', { status: 'accepted' }),
    };
    const { container } = render(<CashCopilotResults runId="run-1" enabled />);
    expect(screen.getByRole('button', { name: /Confirm decisions/i })).toBeInTheDocument();
    expect(container.textContent).toContain('3 decisions staged');
    expect(container.textContent).toContain('(2 accepted, 1 adjusted)');
  });

  it('hides the bar once every staged decision has been confirmed into a PO', () => {
    hoisted.state.byId = {
      a: decision('a', { status: 'accepted', draft_po_id: 'po-1', draft_po_number: 'PO-DRAFT-1' }),
      b: decision('b', {
        status: 'adjusted',
        override_qty: 250,
        draft_po_id: 'po-2',
        draft_po_number: 'PO-DRAFT-2',
      }),
      c: decision('c', { status: 'accepted', draft_po_id: 'po-1', draft_po_number: 'PO-DRAFT-1' }),
    };
    render(<CashCopilotResults runId="run-1" enabled />);
    expect(screen.queryByRole('button', { name: /Confirm decisions/i })).toBeNull();
  });

  it('opens the confirm dialog and calls confirmDecisions with [] on confirm', async () => {
    hoisted.state.byId = {
      a: decision('a', { status: 'accepted' }),
      b: decision('b', { status: 'adjusted', override_qty: 250 }),
    };
    render(<CashCopilotResults runId="run-1" enabled />);

    // Bar → open the dialog.
    fireEvent.click(screen.getByRole('button', { name: /Confirm decisions/i }));
    expect(screen.getByRole('dialog', { name: 'Confirm decisions?' })).toBeInTheDocument();

    // Dialog confirm → the mutation fires with an empty ids list (confirm all).
    fireEvent.click(screen.getByTestId('dialog-confirm'));
    await waitFor(() => expect(hoisted.confirmMutate).toHaveBeenCalledWith([]));
  });
});
