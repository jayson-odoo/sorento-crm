import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import type { ReorderRecommendation } from '../types/reorder.types';
import { REFUSAL } from '../lib/explainerMockStore';
import { ReorderExplanationDialog } from './ReorderExplanationDialog';

// RecordNavigation (the in-popup pager) calls useRouter().
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

// The M5 semantic-layer hooks are react-query-backed. Drive them directly from
// the test so we can exercise the explanation / advisory / Ask surfaces without a
// QueryClientProvider. `vi.hoisted` lets the factory reference these spies.
const { hExplanation, hAdvisory, hAsk } = vi.hoisted(() => ({
  hExplanation: vi.fn(),
  hAdvisory: vi.fn(),
  hAsk: vi.fn(),
}));

vi.mock('../hooks/useExplainer', () => ({
  useRecommendationExplanation: (...a: unknown[]) => hExplanation(...a),
  useRecommendationAdvisory: (...a: unknown[]) => hAdvisory(...a),
  useAskRecommendation: (...a: unknown[]) => hAsk(...a),
}));

// Same reason for the Coverage Timeline panel: react-query-backed, and its own
// states belong to CoverageTimelinePanel.test.tsx. Inert here.
const coverage = vi.hoisted(() => ({
  useCoverageTimeline: vi.fn(() => ({
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  })),
  useAcceptCoverageTransfer: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));
vi.mock('../hooks/useCoverage', () => coverage);

// jsdom polyfills for Radix Dialog / Popover.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

function rec(over: Partial<ReorderRecommendation>): ReorderRecommendation {
  return {
    id: 'rec-1',
    type: 'buy',
    sku: 'ACC-CB9001',
    product_name: 'Ceramic Wash Basin',
    abc_class: 'A',
    xyz_class: 'X',
    warehouse_code: 'WH-KL',
    warehouse_name: 'Kuala Lumpur DC',
    is_network: false,
    allocation: null,
    order_qty: 4,
    recommended_qty: 3.2,
    reorder_point: 8,
    min_qty: null,
    max_qty: null,
    order_up_to: 10,
    net_position: 6,
    days_of_cover: 3,
    reason: 'reorder_point',
    reason_label: 'reorder_point: net 6 <= ROP 8',
    confidence: 'high',
    sample_size: 40,
    supplier: {
      supplier_code: 'SUP-ACME',
      supplier_name: 'Acme Sanitary Sdn Bhd',
      unit_cost: 42,
      lead_time_days: 2,
      composite_score: 88,
      is_primary: true,
    },
    alternatives: [],
    is_exception: false,
    disposition_action: null,
    transfer_flag: null,
    forecast_daily_demand: 1,
    lead_time_days: 2,
    lead_time_source: 'measured',
    safety_stock: 6,
    safety_stock_method: 'fixed_days',
    safety_stock_fallback: null,
    service_level: 0.95,
    safety_days: 7,
    review_days: 30,
    moq: 1,
    order_multiple: 2,
    policy_type: 'reorder_point',
    supplier_selection: 'primary',
    unit_cost: null,
    cash_impact: null,
    rank: null,
    rank_score: null,
    funding_status: null,
    days_to_stockout: null,
    rank_factors: [],
    ...over,
  } as ReorderRecommendation;
}

/** Default: idle explanation with data, no advisory, inert ask mutation. */
function setHooks({
  explanation,
  advisory,
  ask,
}: {
  explanation?: Partial<ReturnType<typeof hExplanation>>;
  advisory?: unknown;
  ask?: { mutateAsync?: ReturnType<typeof vi.fn>; isPending?: boolean };
} = {}) {
  hExplanation.mockReturnValue({
    data: { explanation: 'You should order 4 units now.' },
    isLoading: false,
    isError: false,
    ...explanation,
  });
  hAdvisory.mockReturnValue(advisory ?? { data: { advisory: null } });
  hAsk.mockReturnValue({
    mutateAsync: ask?.mutateAsync ?? vi.fn(),
    isPending: ask?.isPending ?? false,
  });
}

beforeEach(() => {
  hExplanation.mockReset();
  hAdvisory.mockReset();
  hAsk.mockReset();
  setHooks();
});

const dispositionRec = () =>
  rec({
    type: 'disposition',
    sku: 'MX-SHOWER-CHR',
    order_qty: null,
    recommended_qty: null,
    reason: 'overstock',
    reason_label: 'overstock: cover exceeds ceiling',
    days_of_cover: 856,
    net_position: 1731,
    forecast_daily_demand: 0.08,
    xyz_class: 'Z',
    supplier: null,
    disposition_action: 'hold',
  });

/** The AI summary is on demand now: two model calls per open, spent 460 times while
 *  stepping through 230 rows, bought a sentence that restates the numbers below it. Every
 *  test that wants the block has to ask for it, which is the contract. */
function askForTheSummary() {
  // Tolerant on purpose: stepping to another rec resets the ask, but a rerender of the SAME
  // rec keeps it, and a test should not care which of the two it is looking at.
  const trigger = screen.queryByTestId('explain-in-words');
  if (trigger) fireEvent.click(trigger);
}

describe('ReorderExplanationDialog — M5 semantic layer', () => {
  it('costs nothing until it is asked for', () => {
    setHooks({ explanation: { data: { explanation: 'You should order 4 units now.' } } });
    render(<ReorderExplanationDialog rec={rec({})} open onOpenChange={() => {}} />);

    expect(screen.queryByText('AI summary')).toBeNull();
    expect(screen.getByTestId('explain-in-words')).toBeInTheDocument();
  });

  it('renders a skeleton while the explanation is generating, then the sentence', () => {
    setHooks({ explanation: { data: undefined, isLoading: true } });
    const { rerender } = render(
      <ReorderExplanationDialog rec={rec({})} open onOpenChange={() => {}} />,
    );

    askForTheSummary();
    // AI-summary block is present and shows a loading skeleton (no prose yet)
    expect(screen.getByText('AI summary')).toBeInTheDocument();
    expect(document.querySelector('[aria-label="Generating explanation"]')).not.toBeNull();

    // Flip to loaded — the generated sentence renders in place of the skeleton
    setHooks({ explanation: { data: { explanation: 'You should order 4 units now.' } } });
    rerender(<ReorderExplanationDialog rec={rec({})} open onOpenChange={() => {}} />);
    expect(screen.getByText('You should order 4 units now.')).toBeInTheDocument();
    expect(document.querySelector('[aria-label="Generating explanation"]')).toBeNull();
  });

  it('shows an error fallback (not a fabricated sentence) when generation fails', () => {
    setHooks({ explanation: { data: undefined, isLoading: false, isError: true } });
    render(<ReorderExplanationDialog rec={rec({})} open onOpenChange={() => {}} />);
    askForTheSummary();
    expect(screen.getByText('AI summary')).toBeInTheDocument();
    expect(
      screen.getByText(/Couldn.t generate a plain-language summary/i),
    ).toBeInTheDocument();
  });

  it('renders the AI-summary block AND the Ask box for BUY and disposition alike', () => {
    const { rerender } = render(
      <ReorderExplanationDialog rec={rec({})} open onOpenChange={() => {}} />,
    );
    askForTheSummary();
    expect(screen.getByText('AI summary')).toBeInTheDocument();
    // buy recs get the bounded Ask box
    expect(screen.getByText('Ask about this recommendation')).toBeInTheDocument();

    // Disposition rows now get the SAME AI summary + Ask surfaces (a disposition
    // is a real recommendation the planner may want explained / interrogated).
    rerender(
      <ReorderExplanationDialog rec={dispositionRec()} open onOpenChange={() => {}} />,
    );
    askForTheSummary();
    expect(screen.getByText('AI summary')).toBeInTheDocument();
    expect(screen.getByText('Ask about this recommendation')).toBeInTheDocument();
  });

  it('shows the market-advisory callout only when an advisory is present', () => {
    setHooks({ advisory: { data: { advisory: 'Tile prices trending +8% — order sooner.' } } });
    const { rerender } = render(
      <ReorderExplanationDialog rec={rec({})} open onOpenChange={() => {}} />,
    );
    // The advisory is a market-search call, so it rides the same ask as the summary.
    askForTheSummary();
    expect(screen.getByText('Market signal')).toBeInTheDocument();
    expect(screen.getByText(/Tile prices trending \+8%/i)).toBeInTheDocument();

    // No signal → callout hidden.
    setHooks({ advisory: { data: { advisory: null } } });
    rerender(<ReorderExplanationDialog rec={rec({})} open onOpenChange={() => {}} />);
    expect(screen.queryByText('Market signal')).not.toBeInTheDocument();
  });

  it('disables the Ask button until a non-empty question is typed', () => {
    render(<ReorderExplanationDialog rec={rec({})} open onOpenChange={() => {}} />);
    const button = screen.getByRole('button', { name: /ask/i });
    expect(button).toBeDisabled(); // empty input

    fireEvent.change(screen.getByLabelText('Ask about this recommendation'), {
      target: { value: 'What lead time was used?' },
    });
    expect(button).toBeEnabled();

    // whitespace-only is still treated as empty
    fireEvent.change(screen.getByLabelText('Ask about this recommendation'), {
      target: { value: '   ' },
    });
    expect(button).toBeDisabled();
  });

  it('keeps the Ask button disabled while a question is pending', () => {
    setHooks({ ask: { mutateAsync: vi.fn(), isPending: true } });
    render(<ReorderExplanationDialog rec={rec({})} open onOpenChange={() => {}} />);
    fireEvent.change(screen.getByLabelText('Ask about this recommendation'), {
      target: { value: 'anything' },
    });
    expect(screen.getByRole('button', { name: /ask/i })).toBeDisabled();
  });

  it('appends a transcript turn and styles a REFUSAL answer as a muted/italic turn', async () => {
    const mutateAsync = vi.fn().mockResolvedValue({ answer: REFUSAL });
    setHooks({ ask: { mutateAsync } });
    render(<ReorderExplanationDialog rec={rec({})} open onOpenChange={() => {}} />);

    fireEvent.change(screen.getByLabelText('Ask about this recommendation'), {
      target: { value: 'What is the supplier phone number?' },
    });
    fireEvent.click(screen.getByRole('button', { name: /ask/i }));

    // the question is echoed into the transcript…
    expect(
      await screen.findByText('What is the supplier phone number?'),
    ).toBeInTheDocument();
    // …and the refusal answer renders verbatim, styled as a muted/italic turn
    const answer = await screen.findByText(REFUSAL);
    const bubble = answer.closest('div');
    expect(bubble?.className).toContain('italic');
    expect(bubble?.className).toContain('text-muted-foreground');

    expect(mutateAsync).toHaveBeenCalledWith('What is the supplier phone number?');
  });

  it('renders an answerable turn without the refusal (italic) styling', async () => {
    const mutateAsync = vi
      .fn()
      .mockResolvedValue({ answer: 'The lead time used is 2 days (measured).' });
    setHooks({ ask: { mutateAsync } });
    render(<ReorderExplanationDialog rec={rec({})} open onOpenChange={() => {}} />);

    fireEvent.change(screen.getByLabelText('Ask about this recommendation'), {
      target: { value: 'What lead time was used?' },
    });
    fireEvent.click(screen.getByRole('button', { name: /ask/i }));

    const answer = await screen.findByText('The lead time used is 2 days (measured).');
    const bubble = answer.closest('div');
    expect(bubble?.className).not.toContain('italic');
    expect(bubble?.className).toContain('bg-muted');

    // input is cleared after a successful ask
    expect(
      (screen.getByLabelText('Ask about this recommendation') as HTMLInputElement).value,
    ).toBe('');
  });

  it('records a failed ask as a refused turn (no crash, styled muted)', async () => {
    const mutateAsync = vi.fn().mockRejectedValue(new Error('network down'));
    setHooks({ ask: { mutateAsync } });
    render(<ReorderExplanationDialog rec={rec({})} open onOpenChange={() => {}} />);

    fireEvent.change(screen.getByLabelText('Ask about this recommendation'), {
      target: { value: 'why?' },
    });
    fireEvent.click(screen.getByRole('button', { name: /ask/i }));

    const answer = await screen.findByText('network down');
    expect(answer.closest('div')?.className).toContain('italic');
  });
});
