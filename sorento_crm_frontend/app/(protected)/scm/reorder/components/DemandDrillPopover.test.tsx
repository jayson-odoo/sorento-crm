/**
 * DemandDrillPopover (AC-C2.2a / AC-C2.3 / AC-C2.4).
 *
 * The three things this component exists to guarantee:
 *
 * - The aggregate is a FIGURE plus an information icon. The contributing lines
 *    are not on the row and are not fetched until the icon is opened, because
 *    preventing information fatigue is a requirement, not a preference.
 * - Project demand decomposes into project, SO number, quantity and required
 *    date (AC-C2.3).
 * - Retail outstanding decomposes into dealer, SO number, quantity and DAYS
 *    OUTSTANDING, worst-first (AC-C2.4). The 2-unit line that has waited 214 days
 *    renders ABOVE the 96-unit line raised in May, which is the entire reason the
 *    column exists.
 *
 * The real fixtures from `lib/summaryOrderMockStore` are used rather than
 * hand-typed numbers, so a fixture drifting from the ACs fails here too.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

// jsdom polyfills for Radix Popover.
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

const hooks = vi.hoisted(() => ({ useOrderSummaryDemand: vi.fn() }));
vi.mock('../hooks/useSummaryOrder', () => hooks);

import { SUMMARY_ORDER_FIXTURES } from '../lib/summaryOrderMockStore';
import { DemandDrillPopover } from './DemandDrillPopover';

const PROJECT = SUMMARY_ORDER_FIXTURES.demand('B2155-NL-BLUE', 'project');
const DEALER = SUMMARY_ORDER_FIXTURES.demand('B2155-NL-BLUE', 'retail');

function state(over: Record<string, unknown> = {}) {
  return { data: undefined, isLoading: false, isError: false, error: null, refetch: vi.fn(), ...over };
}

function renderDrill(
  hookState: ReturnType<typeof state>,
  over: Partial<React.ComponentProps<typeof DemandDrillPopover>> = {},
) {
  hooks.useOrderSummaryDemand.mockReturnValue(hookState);
  render(
    <DemandDrillPopover
      productCode="B2155-NL-BLUE"
      productName="Basin 2155 Nano-Lite Blue"
      kind="retail"
      totalQty={186}
      lineCount={4}
      runId="run-2026-w32"
      {...over}
    />,
  );
  return hookState;
}

function openDrill() {
  fireEvent.click(screen.getByRole('button', { name: /for B2155-NL-BLUE/i }));
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('DemandDrillPopover - the aggregate stays behind an icon (AC-C2.2a)', () => {
  it('renders the total on the row and NOTHING else until the icon is opened', () => {
    renderDrill(state({ data: DEALER }));
    expect(screen.getByTestId('demand-total-retail')).toHaveTextContent('186');
    // No contributing line is on the row.
    expect(screen.queryByText('Kedai Perabot Seri Muda')).not.toBeInTheDocument();
    expect(screen.queryByTestId('retail-lines')).not.toBeInTheDocument();
  });

  it('does not fetch the lines until the icon is opened', () => {
    renderDrill(state({ data: DEALER }));
    // The last argument is the query's `enabled` flag, which is the open state.
    expect(hooks.useOrderSummaryDemand).toHaveBeenLastCalledWith(
      'B2155-NL-BLUE',
      'retail',
      'run-2026-w32',
      false,
    );
    openDrill();
    expect(hooks.useOrderSummaryDemand).toHaveBeenLastCalledWith(
      'B2155-NL-BLUE',
      'retail',
      'run-2026-w32',
      true,
    );
  });

  it('renders no icon when nothing contributes, rather than an icon that opens nothing', () => {
    renderDrill(state({ data: DEALER }), { lineCount: 0, totalQty: 0 });
    expect(screen.getByTestId('demand-total-retail')).toHaveTextContent('0');
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});

describe('DemandDrillPopover - states', () => {
  it('shows a skeleton while the lines are being fetched', () => {
    renderDrill(state({ isLoading: true }));
    openDrill();
    expect(screen.getByLabelText('Loading contributing lines')).toBeInTheDocument();
  });

  it('shows the backend message and a retry when the drill fails', () => {
    const s = renderDrill(state({ isError: true, error: new Error('Unknown product code') }));
    openDrill();
    expect(screen.getByText('Unknown product code')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Try again/i }));
    expect(s.refetch).toHaveBeenCalled();
  });

  it('says nothing is outstanding rather than rendering an empty list', () => {
    renderDrill(
      state({ data: { ...DEALER, retail_lines: [], dealer_lines: [], total_qty: 0 } }),
      { totalQty: 0 },
    );
    openDrill();
    expect(screen.getByText('No retail order is outstanding on this item.')).toBeInTheDocument();
  });
});

describe('DemandDrillPopover - project demand (AC-C2.3)', () => {
  it('names the project, the sales order, the quantity and the required date', () => {
    renderDrill(state({ data: PROJECT }), { kind: 'project', totalQty: 480, lineCount: 3 });
    openDrill();
    const lines = screen.getByTestId('project-lines');
    expect(within(lines).getByText('Maryam Tuju Residence')).toBeInTheDocument();
    expect(within(lines).getByText(/SO-2026-0311/)).toBeInTheDocument();
    expect(lines).toHaveTextContent('needed 15/09/2026');
    expect(within(lines).getByText('260')).toBeInTheDocument();
  });

  it('sums to the aggregate shown on the row - the row figure is derived, never retyped', () => {
    const total = PROJECT.project_lines.reduce((sum, l) => sum + l.qty, 0);
    expect(total).toBe(480);
    expect(PROJECT.total_qty).toBe(480);
  });
});

describe('DemandDrillPopover - retail ageing, worst-first (AC-C2.4)', () => {
  it('shows days outstanding for every line', () => {
    renderDrill(state({ data: DEALER }));
    openDrill();
    const lines = screen.getByTestId('retail-lines');
    expect(within(lines).getByText('214 days')).toBeInTheDocument();
    expect(within(lines).getByText('91 days')).toBeInTheDocument();
    expect(within(lines).getByText('33 days')).toBeInTheDocument();
    expect(within(lines).getByText('8 days')).toBeInTheDocument();
  });

  it('renders the 2-unit line that waited 214 days ABOVE the 96-unit line raised in May', () => {
    renderDrill(state({ data: DEALER }));
    openDrill();
    const rendered = screen.getByTestId('retail-lines').textContent ?? '';
    expect(rendered.indexOf('Kedai Perabot Seri Muda')).toBeLessThan(
      rendered.indexOf('Hup Seng Hardware'),
    );
    // And the order is the SERVER's - the component does not re-sort.
    expect(DEALER.retail_lines.map((l) => l.days_outstanding)).toEqual([214, 91, 33, 8]);
  });

  it('names the dealer and the sales order, never an internal id', () => {
    renderDrill(state({ data: DEALER }));
    openDrill();
    const lines = screen.getByTestId('retail-lines');
    expect(within(lines).getByText('Kedai Perabot Seri Muda')).toBeInTheDocument();
    expect(within(lines).getByText(/SO-2025-1188/)).toBeInTheDocument();
    expect(lines.textContent).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-/i);
  });
});

describe('the trailing-window header speaks for the drilled row only (P5)', () => {
  // The backend sends both figures on every drill; `kind` is what makes one of them
  // this row's answer. The fixtures predate the fields, so they are added here.
  const withContext = (over: Record<string, unknown> = {}) => ({
    ...DEALER,
    project_12m_qty: 120,
    retail_3m_qty: 30,
    project_window_months: 12,
    retail_window_months: 3,
    ...over,
  });

  it('a project drill states the project year, and no retail quarter', () => {
    renderDrill(state({ data: withContext({ ...PROJECT }) }), { kind: 'project' });
    openDrill();

    expect(screen.getByText('Project, last 12 full months: 120')).toBeInTheDocument();
    expect(screen.queryByText(/Retail, last/)).not.toBeInTheDocument();
  });

  it('a retail drill states the retail quarter, and no project year', () => {
    renderDrill(state({ data: withContext() }), { kind: 'retail' });
    openDrill();

    expect(screen.getByText('Retail, last 3 full months: 30')).toBeInTheDocument();
    expect(screen.queryByText(/Project, last/)).not.toBeInTheDocument();
  });

  it('says nothing at all when the drilled channel has no figure of its own', () => {
    renderDrill(state({ data: withContext({ project_12m_qty: null }) }), { kind: 'project' });
    openDrill();

    expect(screen.queryByText(/full months/)).not.toBeInTheDocument();
  });
});
