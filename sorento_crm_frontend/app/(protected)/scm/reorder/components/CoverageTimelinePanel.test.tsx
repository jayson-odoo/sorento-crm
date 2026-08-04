/**
 * CoverageTimelinePanel (UAC Group B) - loading / empty / error / data, plus the
 * two cases that are the reason the slice exists:
 *
 *  - AC-B4: a POSITIVE closing balance with a REAL shortfall must not read as
 *    healthy. The ADR-0011 worked example (opening 140, -135 due 1 Jul, -72 due
 *    3 Aug, +200 arriving 25 Aug) closes at +133 while being 67 short on 3 Aug.
 *    The shortfall must be stated, the late PO named with the 22-day gap, and the
 *    closing figure captioned as not clearing it.
 *  - AC-B1c: demand 67 against a pool holding 4,397 must read "use the pool" and
 *    never a buy of 67.
 *
 * The real fixtures from `lib/coverageMockStore` are used rather than hand-typed
 * numbers, so a fixture drifting from the ACs fails here too.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';

// jsdom polyfills for ScrollArea / DataGrid / AlertDialog.
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

vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/reorder',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const hooks = vi.hoisted(() => ({
  useCoverageTimeline: vi.fn(),
  useAcceptCoverageTransfer: vi.fn(),
}));
vi.mock('../hooks/useCoverage', () => hooks);

import { COVERAGE_FIXTURES } from '../lib/coverageMockStore';
import { CoverageTimelinePanel } from './CoverageTimelinePanel';
import type { CoverageTimeline } from '../types/coverage.types';

const SHORTFALL = COVERAGE_FIXTURES.shortfall();
const USE_POOL = COVERAGE_FIXTURES.use_pool();
const HEALTHY = COVERAGE_FIXTURES.healthy();
const UNDATED = COVERAGE_FIXTURES.undated();
const EMPTY = COVERAGE_FIXTURES.empty();

const mutate = vi.fn();

function state(over: Record<string, unknown> = {}) {
  return {
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...over,
  };
}

function renderPanel(
  hookState: ReturnType<typeof state>,
  over: Partial<React.ComponentProps<typeof CoverageTimelinePanel>> = {},
) {
  hooks.useCoverageTimeline.mockReturnValue(hookState);
  render(
    <CoverageTimelinePanel
      productCode="SRTBS4832"
      productName="Basin mixer 4832"
      poolCode="BRW-BB"
      floor={0}
      enabled
      {...over}
    />,
  );
  return hookState;
}

function withData(timeline: CoverageTimeline, over = {}) {
  return renderPanel(state({ data: timeline }), over);
}

beforeEach(() => {
  vi.clearAllMocks();
  hooks.useAcceptCoverageTransfer.mockReturnValue({ mutate, isPending: false });
});

describe('CoverageTimelinePanel - states', () => {
  it('shows a skeleton while the timeline is being computed', () => {
    renderPanel(state({ isLoading: true }));
    expect(screen.getByLabelText('Loading coverage timeline')).toBeInTheDocument();
    expect(screen.queryByTestId('coverage-verdict')).not.toBeInTheDocument();
  });

  it('shows the backend message and a retry when it fails', () => {
    const s = renderPanel(
      state({ isError: true, error: new Error('Unknown pool code BRW-ZZ') }),
    );
    expect(screen.getByText('Unknown pool code BRW-ZZ')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Try again/i }));
    expect(s.refetch).toHaveBeenCalled();
  });

  it('states that nothing is dated, with the on-hand figure, rather than rendering a blank grid', () => {
    withData(EMPTY);
    expect(screen.getByText('Nothing dated against this stock')).toBeInTheDocument();
    expect(screen.getByText(/24 on hand, no open order or supply/i)).toBeInTheDocument();
  });

  it('renders every section for a network row instead of hiding the panel', () => {
    withData(HEALTHY, { poolCode: null });
    expect(screen.getByText(/planned across the network/i)).toBeInTheDocument();
    // Nothing is fetched for a row with no single pool.
    expect(screen.queryByTestId('coverage-verdict')).not.toBeInTheDocument();
  });

  it('renders the dated movements with their running balances and month headings', () => {
    withData(SHORTFALL);
    const timeline = screen.getByRole('region', { name: 'Coverage timeline' });
    // Every event names a document a person recognises - no UUID (AC-B2).
    expect(within(timeline).getByText('SO-2026-0311')).toBeInTheDocument();
    expect(within(timeline).getByText('SO-2026-0342')).toBeInTheDocument();
    expect(within(timeline).getByText('PO-2026-0442')).toBeInTheDocument();
    // Balances 140 -> 5 -> -67 -> 133, as accumulated by the server.
    expect(within(timeline).getByText('5')).toBeInTheDocument();
    expect(within(timeline).getByText('−67')).toBeInTheDocument();
    // Months are display grouping only (AC-B3).
    expect(within(timeline).getByText('Jul 2026')).toBeInTheDocument();
    expect(within(timeline).getByText('Aug 2026')).toBeInTheDocument();
  });
});

describe('CoverageTimelinePanel - a positive closing balance with a real shortfall (AC-B4)', () => {
  it('states the shortfall quantity and date before any balance', () => {
    withData(SHORTFALL);
    const banner = screen.getByTestId('coverage-shortfall');
    expect(banner).toHaveTextContent('Short 67 on 03 Aug 2026');
    expect(banner).toHaveTextContent('SO-2026-0342');
  });

  it('names the supply that arrives too late and by how many days', () => {
    withData(SHORTFALL);
    const banner = screen.getByTestId('coverage-shortfall');
    // The PO of 200 lands 25 Aug against an order due 3 Aug: 22 days late.
    expect(banner).toHaveTextContent('PO-2026-0442');
    expect(banner).toHaveTextContent('25 Aug 2026');
    expect(banner).toHaveTextContent('22 days too late');
  });

  it('does NOT present the positive closing balance as healthy', () => {
    withData(SHORTFALL);
    const closing = screen.getByTestId('coverage-closing');
    expect(closing).toHaveTextContent('133');
    // The caption is what stops +133 reading as covered.
    expect(closing).toHaveTextContent('does not clear the shortfall on 03 Aug 2026');
    // And it is never given the healthy tone.
    expect(closing.querySelector('.text-scm-incoming')).toBeNull();
  });

  it('shows the peak deficit, which a later event can dig deeper than the first', () => {
    withData(SHORTFALL);
    expect(screen.getByTestId('coverage-peak')).toHaveTextContent('67');
  });

  it('shows the on-order / in-transit split beside the incoming total', () => {
    withData(SHORTFALL);
    expect(screen.getByTestId('coverage-incoming')).toHaveTextContent('200 on order');
    expect(screen.getByTestId('coverage-incoming')).toHaveTextContent('0 in transit');
  });

  it('keeps in-transit separate from on-order when the supply has shipped', () => {
    withData(HEALTHY);
    expect(screen.getByTestId('coverage-incoming')).toHaveTextContent('0 on order');
    expect(screen.getByTestId('coverage-incoming')).toHaveTextContent('400 in transit');
  });
});

describe('CoverageTimelinePanel - use the pool, do not buy (AC-B1c)', () => {
  it('reads "Use the pool" and buys nothing when the pool covers the line', () => {
    withData(USE_POOL);
    expect(screen.getByTestId('coverage-verdict')).toHaveTextContent('Use the pool (BRW)');
    expect(screen.getByText(/Buy 0 · existing stock covers it/)).toBeInTheDocument();
    // The regression: demand 67 against 4,397 must never propose buying 67.
    expect(screen.queryByText('Buy 67')).not.toBeInTheDocument();
  });

  it('splits what is available by source, naming the pool and the other bins', () => {
    withData(USE_POOL);
    const sources = screen.getByRole('region', { name: 'Cover sources' });
    expect(within(sources).getByText('4,397')).toBeInTheDocument();
    expect(within(sources).getByText('126')).toBeInTheDocument();
    expect(within(sources).getByText('BRW-NTC')).toBeInTheDocument();
  });

  it('reads "Buy" with the quantity and flags cover that needs another holder to agree', () => {
    withData(SHORTFALL);
    expect(screen.getByTestId('coverage-verdict')).toHaveTextContent('Buy 49');
    const sources = screen.getByRole('region', { name: 'Cover sources' });
    expect(within(sources).getByText("Another holder's bin")).toBeInTheDocument();
    expect(within(sources).getByText('needs a claim')).toBeInTheDocument();
    expect(within(sources).getByText('Purchase')).toBeInTheDocument();
  });

  it('says there is nothing to resolve rather than leaving the section blank', () => {
    withData(HEALTHY);
    const sources = screen.getByRole('region', { name: 'Cover sources' });
    expect(within(sources).getByText(/Nothing to resolve/i)).toBeInTheDocument();
  });
});

describe('CoverageTimelinePanel - undated demand, horizon and transfers', () => {
  it('lists undated commitments rather than hiding them or dating them today', () => {
    withData(UNDATED);
    const section = screen.getByRole('region', { name: 'Undated demand' });
    expect(within(section).getByText('SO-2026-0374')).toBeInTheDocument();
    expect(within(section).getByText('SO-2026-0381')).toBeInTheDocument();
    expect(within(section).getByText(/cannot be placed on the axis/i)).toBeInTheDocument();
  });

  it('states the horizon exclusion on screen, never silently (AC-B5)', () => {
    withData(UNDATED);
    expect(
      screen.getByText(/3 events beyond 31 Jul 2027 excluded \(12-month horizon\)/i),
    ).toBeInTheDocument();
  });

  it('says every commitment is dated when there is no undated demand', () => {
    withData(HEALTHY);
    const section = screen.getByRole('region', { name: 'Undated demand' });
    expect(within(section).getByText('Every commitment carries a date.')).toBeInTheDocument();
  });

  it('shows cross-site cover as a proposal with its cost and lead time, not netted (AC-B1d)', () => {
    withData(SHORTFALL);
    const section = screen.getByRole('region', { name: 'Transfer proposals' });
    expect(within(section).getByText('MWH')).toBeInTheDocument();
    expect(within(section).getByText('RM 480')).toBeInTheDocument();
    expect(within(section).getByText('5')).toBeInTheDocument();
    expect(within(section).getByText('08 Aug 2026')).toBeInTheDocument();
    expect(within(section).getByText(/Not counted in the balance above/i)).toBeInTheDocument();
  });

  it('never renders the proposal_ref, which is a key and not information', () => {
    withData(SHORTFALL);
    expect(screen.queryByText('TP-MWH-0001')).not.toBeInTheDocument();
  });

  it('confirms before accepting a transfer, stating the cost and the lead time', async () => {
    withData(SHORTFALL);
    const section = screen.getByRole('region', { name: 'Transfer proposals' });
    fireEvent.click(within(section).getByRole('button', { name: /Accept/i }));

    const dialog = await screen.findByRole('alertdialog');
    expect(dialog).toHaveTextContent('Accept this transfer?');
    expect(dialog).toHaveTextContent('moves 67 of SRTBS4832 from MWH to BRW');
    expect(dialog).toHaveTextContent('RM 480');
    expect(dialog).toHaveTextContent('5 days lead time');
    // Nothing happens until the confirmation is given.
    expect(mutate).not.toHaveBeenCalled();

    fireEvent.click(within(dialog).getByRole('button', { name: /Accept transfer/i }));
    await waitFor(() => expect(mutate).toHaveBeenCalledWith('TP-MWH-0001'));
  });

  it('says no other site holds the item when there is no proposal', () => {
    withData(HEALTHY);
    const section = screen.getByRole('region', { name: 'Transfer proposals' });
    expect(within(section).getByText('No other site holds this item.')).toBeInTheDocument();
  });

  it('renders computed_at as written, without shifting it out of Malaysia time', () => {
    withData(SHORTFALL);
    // The fixture is 2026-08-03T09:12:00, already Malaysia wall-clock.
    expect(screen.getByTestId('coverage-verdict')).toHaveTextContent('Computed 03 Aug 2026, 09:12');
  });
});
