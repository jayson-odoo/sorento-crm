/**
 * ProductSetProposals - the review screen a person ticks candidates on before
 * anything is written. Three behaviours here were previously proven only by a
 * one-off browser run, and all three are regressions waiting to happen:
 *
 * 1. The discontinued badge: 41 of 136 live candidates carry a discontinued
 *    member, and the card was previously pixel-identical to a healthy one.
 * 2. "Scan again" confirms before it replaces the batch, and clears the ticks
 *    on confirm - the sticky bar used to keep claiming "40 ticked" over a
 *    screen where nothing was checked, and Create then fired 40 dead ids.
 * 3. Money renders with cents - `1180` must read `RM 1,180.00`, not `RM 1,180`.
 *
 * UAC group H: `documentation/plans/master-data/product-sets-acceptance-criteria.md`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within, act } from '@testing-library/react';

const useProductSetProposals = vi.hoisted(() => vi.fn());
const useRunProductSetProposals = vi.hoisted(() => vi.fn());
const useApplyProductSetProposals = vi.hoisted(() => vi.fn());

vi.mock('../hooks/useProductSetProposals', () => ({
  useProductSetProposals,
  useRunProductSetProposals,
  useApplyProductSetProposals,
}));

import ProductSetProposals from './ProductSetProposals';
import type {
  ProductSetProposal,
  ProductSetProposalBatch,
} from '../types/productSetProposal.types';

function member(overrides: Partial<ProductSetProposal['members'][number]> = {}) {
  return {
    product_code: 'SRTWC8608P',
    description: 'Pedestal',
    list_price: 1180,
    quantity: 1,
    contributes_to_price: true,
    sort_order: 0,
    is_discontinued: false,
    ...overrides,
  };
}

function proposal(overrides: Partial<ProductSetProposal> = {}): ProductSetProposal {
  return {
    id: 'proposal-1',
    family_key: 'SRTWC8608',
    set_code: 'SRTWC8608',
    name: 'Sorento close coupled set',
    members: [member()],
    computed_price: 1180,
    ...overrides,
  };
}

function batch(overrides: Partial<ProductSetProposalBatch> = {}): ProductSetProposalBatch {
  const proposals = overrides.proposals ?? [proposal()];
  return {
    id: 'batch-1',
    company_name: 'Sorento',
    created_at: '2026-08-24T00:00:00Z',
    created_by_name: 'Jane Tan',
    family_count: 1,
    proposal_count: proposals.length,
    proposals,
    ...overrides,
  };
}

/** Every ProposalCard renders inside a `.rounded-lg border` wrapper the family
 *  group Card (`rounded-xl`) does not share, so this scopes assertions to one
 *  card without depending on DOM order. */
function cardFor(setCode: string): HTMLElement {
  const el = screen.getByRole('checkbox', { name: `Create ${setCode}` }).closest('.rounded-lg');
  if (!el) throw new Error(`No card wrapper found for ${setCode}`);
  return el as HTMLElement;
}

/** The sticky bar's "N ticked" count sits in its own nested `<span>`, so
 *  `getByText` (which matches a node's own direct text, not its descendants'
 *  aggregated text) cannot find the literal string "1 ticked". The sticky bar
 *  itself is only rendered while something is ticked, so its presence -
 *  confirmed here via the "Clear" button it carries - is the count that matters. */
function stickyBar(): HTMLElement | null {
  return screen.queryByRole('button', { name: /^clear$/i });
}

beforeEach(() => {
  useProductSetProposals.mockReset();
  useRunProductSetProposals.mockReset();
  useApplyProductSetProposals.mockReset();
  useRunProductSetProposals.mockReturnValue({ mutate: vi.fn(), isPending: false });
  useApplyProductSetProposals.mockReturnValue({
    mutateAsync: vi.fn(),
    isPending: false,
  });
});

describe('ProductSetProposals - discontinued badge', () => {
  it('shows the count badge on the collapsed card, and the per-member badge once expanded', () => {
    const healthy = proposal({
      id: 'p-healthy',
      set_code: 'SRTWC8608',
      members: [member({ product_code: 'SRTWC8608P', is_discontinued: false })],
    });
    const withDiscontinued = proposal({
      id: 'p-discontinued',
      set_code: 'SRTWC8609',
      members: [
        member({ product_code: 'SRTWC8609P', is_discontinued: true }),
        member({ product_code: 'SRTWC8609C', is_discontinued: false }),
      ],
    });
    useProductSetProposals.mockReturnValue({
      data: batch({ proposals: [healthy, withDiscontinued] }),
      isLoading: false,
      isError: false,
      error: null,
    });

    render(<ProductSetProposals />);

    // Healthy proposal: no discontinued badge anywhere, collapsed or expanded.
    const healthyCard = cardFor('SRTWC8608');
    expect(within(healthyCard).queryByText(/discontinued/i)).not.toBeInTheDocument();

    // Proposal with a discontinued member: badge visible on the COLLAPSED card.
    const flaggedCard = cardFor('SRTWC8609');
    expect(within(flaggedCard).getByText('1 discontinued')).toBeInTheDocument();
    // The per-member badge is not rendered until the card is expanded.
    expect(within(flaggedCard).queryByText('Discontinued')).not.toBeInTheDocument();

    // Expand it - the per-member badge now shows on the discontinued row only.
    fireEvent.click(within(flaggedCard).getByText('SRTWC8609'));
    expect(within(flaggedCard).getByText('Discontinued')).toBeInTheDocument();
    const rows = within(flaggedCard).getAllByRole('row');
    // header row + 2 member rows
    expect(rows).toHaveLength(3);
    expect(within(rows[1]).getByText('Discontinued')).toBeInTheDocument();
    expect(within(rows[2]).queryByText('Discontinued')).not.toBeInTheDocument();
  });
});

describe('ProductSetProposals - Scan again confirms and clears ticks', () => {
  it('opens an AlertDialog rather than scanning immediately; cancel leaves the batch and ticks alone', () => {
    const runMutate = vi.fn();
    useRunProductSetProposals.mockReturnValue({ mutate: runMutate, isPending: false });
    useProductSetProposals.mockReturnValue({
      data: batch({ proposals: [proposal({ id: 'p-1', set_code: 'SRTWC8608' })] }),
      isLoading: false,
      isError: false,
      error: null,
    });

    render(<ProductSetProposals />);

    fireEvent.click(screen.getByRole('checkbox', { name: 'Create SRTWC8608' }));
    expect(stickyBar()).toBeInTheDocument();
    expect(stickyBar()!.closest('[data-slot="card"]')).toHaveTextContent('1 ticked');

    fireEvent.click(screen.getByRole('button', { name: /scan again/i }));
    expect(runMutate).not.toHaveBeenCalled();

    const dialog = screen.getByRole('alertdialog');
    expect(within(dialog).getByText('Scan the catalogue again?')).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole('button', { name: /^cancel$/i }));
    expect(runMutate).not.toHaveBeenCalled();
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    // The batch and the tick are untouched.
    expect(stickyBar()).toBeInTheDocument();
    expect(stickyBar()!.closest('[data-slot="card"]')).toHaveTextContent('1 ticked');
    expect(screen.getByRole('checkbox', { name: 'Create SRTWC8608' })).toBeChecked();
  });

  it('confirming runs the pass and empties the selection', () => {
    const runMutate = vi.fn();
    useRunProductSetProposals.mockReturnValue({ mutate: runMutate, isPending: false });
    useProductSetProposals.mockReturnValue({
      data: batch({ proposals: [proposal({ id: 'p-1', set_code: 'SRTWC8608' })] }),
      isLoading: false,
      isError: false,
      error: null,
    });

    render(<ProductSetProposals />);

    fireEvent.click(screen.getByRole('checkbox', { name: 'Create SRTWC8608' }));
    expect(stickyBar()).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /scan again/i }));
    const dialog = screen.getByRole('alertdialog');
    fireEvent.click(within(dialog).getByRole('button', { name: /^scan again$/i }));

    expect(runMutate).toHaveBeenCalledTimes(1);
    const [, options] = runMutate.mock.calls[0];
    expect(typeof options.onSuccess).toBe('function');

    // Simulate the mutation succeeding - the component's own onSuccess clears the ticks.
    act(() => {
      options.onSuccess();
    });

    expect(stickyBar()).not.toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Create SRTWC8608' })).not.toBeChecked();
  });
});

describe('ProductSetProposals - money renders with cents', () => {
  it('renders a computed_price of 1180 as RM 1,180.00, not RM 1,180', () => {
    useProductSetProposals.mockReturnValue({
      data: batch({
        proposals: [proposal({ id: 'p-1', set_code: 'SRTWC8608', computed_price: 1180 })],
      }),
      isLoading: false,
      isError: false,
      error: null,
    });

    render(<ProductSetProposals />);

    expect(screen.getByText('RM 1,180.00')).toBeInTheDocument();
    expect(screen.queryByText('RM 1,180')).not.toBeInTheDocument();
  });
});
