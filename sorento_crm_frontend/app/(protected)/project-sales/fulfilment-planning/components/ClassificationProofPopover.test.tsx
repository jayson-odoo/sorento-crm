/**
 * The Proof button: the ranked evidence behind one item's hot/cold verdict.
 *
 * The captain, reading the trail: "don't give me jargon like abc classification, just tell
 * me hot selling or cold selling, at project or retail, with some button for me to view
 * detail as a proof ... like for this, you say dealer hot selling, what's the figure, and
 * what's the detail, I need proof". This is that button, and the word "ABC" must never
 * appear anywhere it renders.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const getClassificationEvidence = vi.fn();

vi.mock('../../_shared/services/fulfilmentPlanningService', () => ({
  getClassificationEvidence: (...args: unknown[]) => getClassificationEvidence(...args),
}));

import { ClassificationProofPopover } from './ClassificationProofPopover';
import type { ClassificationEvidence } from '../../_shared/types/fulfilmentPlanning.types';

function evidence(overrides: Partial<ClassificationEvidence> = {}): ClassificationEvidence {
  return {
    product_id: 'prod-1',
    item_code: 'B2155-NL-BLUE',
    computed_at: '2026-08-15T03:00:00',
    window_days: 365,
    hot_cut_pct: 80,
    classes: [
      {
        demand_class: 'retail',
        label: 'Dealer',
        verdict: 'hot',
        locations: [
          {
            warehouse_code: 'BRW',
            qty_delivered: '10',
            rank: 836,
            of: 1901,
            share_pct: 0.02,
            cumulative_share_pct: 93.62,
            letter: 'A',
            hot: true,
          },
        ],
      },
      {
        demand_class: 'project',
        label: 'Project',
        verdict: 'unclassified',
        locations: [],
      },
    ],
    ...overrides,
  };
}

function renderPopover(productId: string | null = 'prod-1') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ClassificationProofPopover productId={productId} testId="line-1" />
    </QueryClientProvider>,
  );
}

function openPopover() {
  fireEvent.click(screen.getByTestId('classification-proof-line-1'));
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ClassificationProofPopover', () => {
  it('renders nothing when there is no product to ask about', () => {
    renderPopover(null);

    expect(screen.queryByTestId('classification-proof-line-1')).not.toBeInTheDocument();
  });

  it('does not fetch until the button is pressed', () => {
    renderPopover();

    expect(getClassificationEvidence).not.toHaveBeenCalled();
  });

  it('fetches by product id once opened, and shows the aria-label the plan asked for', async () => {
    getClassificationEvidence.mockResolvedValue(evidence());

    renderPopover();
    const button = screen.getByTestId('classification-proof-line-1');
    expect(button).toHaveAttribute('aria-label', 'Why hot or cold');

    openPopover();

    await waitFor(() => expect(getClassificationEvidence).toHaveBeenCalledWith('prod-1'));
  });

  it('shows a loading skeleton while the evidence is in flight', () => {
    getClassificationEvidence.mockReturnValue(new Promise(() => {}));

    renderPopover();
    openPopover();

    expect(
      screen.getByTestId('classification-proof-content-line-1').querySelector('[data-slot="skeleton"]'),
    ).toBeInTheDocument();
  });

  it('shows an error line when the evidence fails to load', async () => {
    getClassificationEvidence.mockRejectedValue(new Error('boom'));

    renderPopover();
    openPopover();

    expect(await screen.findByText('Could not load the evidence for this item.')).toBeInTheDocument();
  });

  it('renders the hot row with location, quantity, rank, its own share, and what ranked above it', async () => {
    getClassificationEvidence.mockResolvedValue(evidence());

    renderPopover();
    openPopover();

    const content = screen.getByTestId('classification-proof-content-line-1');
    await waitFor(() => expect(content).toHaveTextContent('Dealer (retail customers)'));
    expect(content).toHaveTextContent('Hot');
    expect(content).toHaveTextContent('BRW');
    expect(content).toHaveTextContent('10');
    expect(content).toHaveTextContent('836 of 1901');
    // Its own weight, never the cumulative figure a thin ranking's top row could be misread
    // as (the captain: "Share: top 93.6%" read as good on a row that held almost nothing).
    expect(content).toHaveTextContent('0.02%');
    expect(content).toHaveTextContent('93.6% of retail quantity');
    expect(content).toHaveTextContent(
      'Hot = among the items that together make the first 80% of quantity delivered to retail customers at that location',
    );
  });

  it('says there were no deliveries at all for an unclassified class, no fabricated row', async () => {
    getClassificationEvidence.mockResolvedValue(evidence());

    renderPopover();
    openPopover();

    const content = screen.getByTestId('classification-proof-content-line-1');
    await waitFor(() => expect(content).toHaveTextContent('Project'));
    expect(content).toHaveTextContent(
      'No project deliveries of this item in the last 12 months.',
    );
  });

  it('never prints the word ABC anywhere, in any class', async () => {
    getClassificationEvidence.mockResolvedValue(
      evidence({
        classes: [
          {
            demand_class: 'retail',
            label: 'Dealer',
            verdict: 'cold',
            locations: [
              {
                warehouse_code: 'HQ',
                qty_delivered: '50',
                rank: 2,
                of: 2,
                cumulative_share_pct: 100,
                letter: 'B',
                hot: false,
              },
            ],
          },
          { demand_class: 'project', label: 'Project', verdict: 'unclassified', locations: [] },
        ],
      }),
    );

    renderPopover();
    openPopover();

    const content = screen.getByTestId('classification-proof-content-line-1');
    await waitFor(() => expect(content).toHaveTextContent('Cold'));
    expect(content.textContent).not.toMatch(/ABC/);
  });
});
