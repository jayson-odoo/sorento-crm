/**
 * ProductLocationsPopover (AC-F07 / AC-F08 / AC-F11 / AC-F12).
 *
 * The three things this drill exists to guarantee:
 *
 * - Demand is split by channel (Project / Retail), supply is NOT:
 *    stock, incoming SPO, PO and the reorder level are printed ONCE per location
 *    row, with no channel dimension (AC-F07).
 * - The once-rounded product figure ("Suggested once at the product") and the
 *    chosen quantity are restated beside the split, so a reader can check the
 *    location quantities sum exactly to the chosen one (AC-E06 / AC-F11 / AC-F12).
 * - A legacy run states its channel breakdown is unavailable rather than
 *    inventing one, and every null channel cell says "Unavailable" instead of 0
 *    (AC-F10).
 *
 * The real fixtures from `lib/summaryOrderMockStore` are used for the data state,
 * so a fixture drifting from the ACs fails here too.
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

const hooks = vi.hoisted(() => ({ useOrderSummaryLocations: vi.fn() }));
vi.mock('../hooks/useSummaryOrder', () => hooks);

import { SUMMARY_ORDER_FIXTURES } from '../lib/summaryOrderMockStore';
import { ProductLocationsPopover } from './ProductLocationsPopover';
import type { OrderSummaryLocations } from '../types/summaryOrder.types';

const BLUE_LOCATIONS = SUMMARY_ORDER_FIXTURES.locations('B2155-NL-BLUE');

function state(over: Record<string, unknown> = {}) {
  return { data: undefined, isLoading: false, isError: false, error: null, refetch: vi.fn(), ...over };
}

function renderPopover(
  hookState: ReturnType<typeof state>,
  over: Partial<React.ComponentProps<typeof ProductLocationsPopover>> = {},
) {
  hooks.useOrderSummaryLocations.mockReturnValue(hookState);
  render(
    <ProductLocationsPopover
      productCode="B2155-NL-BLUE"
      productName="Basin 2155 Nano-Lite Blue"
      runId="run-2026-w32"
      decimalPlaces={0}
      {...over}
    />,
  );
  return hookState;
}

function openPopover() {
  fireEvent.click(screen.getByRole('button', { name: /Member locations for B2155-NL-BLUE/i }));
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ProductLocationsPopover - lazy on open', () => {
  it('does not fetch the locations until the drill is opened', () => {
    renderPopover(state({ data: BLUE_LOCATIONS }));
    expect(hooks.useOrderSummaryLocations).toHaveBeenLastCalledWith(
      'B2155-NL-BLUE',
      'run-2026-w32',
      false,
    );
    openPopover();
    expect(hooks.useOrderSummaryLocations).toHaveBeenLastCalledWith(
      'B2155-NL-BLUE',
      'run-2026-w32',
      true,
    );
  });
});

describe('ProductLocationsPopover - loading state', () => {
  it('shows a skeleton while the member locations load', () => {
    renderPopover(state({ isLoading: true }));
    openPopover();
    expect(screen.getByLabelText('Loading member locations')).toBeInTheDocument();
  });
});

describe('ProductLocationsPopover - error state', () => {
  it('shows the backend message and a retry when the drill fails', () => {
    const s = renderPopover(state({ isError: true, error: new Error('Locations service down') }));
    openPopover();
    expect(screen.getByText('Locations service down')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Try again/i }));
    expect(s.refetch).toHaveBeenCalled();
  });

  it('falls back to a generic message when the error carries none', () => {
    renderPopover(state({ isError: true, error: null }));
    openPopover();
    expect(screen.getByText('Failed to load the member locations.')).toBeInTheDocument();
  });
});

describe('ProductLocationsPopover - empty locations', () => {
  it('states the product holds no stock or demand anywhere, rather than an empty table', () => {
    const empty: OrderSummaryLocations = {
      product_code: 'SRTAC0904',
      decision_grain: 'product',
      is_legacy: false,
      uom: 'PCS',
      uom_decimal_places: 0,
      suggested_qty: 0,
      chosen_qty: null,
      locations: [],
    };
    renderPopover(state({ data: empty }), { productCode: 'SRTAC0904' });
    fireEvent.click(screen.getByRole('button', { name: /Member locations for SRTAC0904/i }));
    expect(
      screen.getByText('This product holds no stock and no demand at any location in this plan.'),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('location-rows')).not.toBeInTheDocument();
  });
});

describe('ProductLocationsPopover - data state (AC-F07 / AC-F08)', () => {
  it('names the warehouse rows with their velocity', () => {
    renderPopover(state({ data: BLUE_LOCATIONS }));
    openPopover();
    const rows = screen.getByTestId('location-rows');
    expect(within(rows).getByText('BRW')).toBeInTheDocument();
    expect(within(rows).getByText('JB')).toBeInTheDocument();
    expect(rows).toHaveTextContent('2.1/day');
    expect(rows).toHaveTextContent('1.5/day');
  });

  it('renders two per-channel demand columns, and never an Unclassified one', () => {
    renderPopover(state({ data: BLUE_LOCATIONS }));
    openPopover();
    const rows = screen.getByTestId('location-rows');
    expect(screen.getByRole('columnheader', { name: 'Project need' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Retail need' })).toBeInTheDocument();
    expect(
      screen.queryByRole('columnheader', { name: 'Unclass. need' }),
    ).not.toBeInTheDocument();
    const brw = within(rows).getByText('BRW').closest('tr') as HTMLElement;
    expect(brw).toHaveTextContent('120'); // project_need
    expect(brw).toHaveTextContent('55'); // retail_need
  });

  it('prints the shared supply figures ONCE per location, with no channel dimension', () => {
    renderPopover(state({ data: BLUE_LOCATIONS }));
    openPopover();
    const rows = screen.getByTestId('location-rows');
    const brw = within(rows).getByText('BRW').closest('tr') as HTMLElement;
    expect(brw).toHaveTextContent('60'); // on_hand
    expect(brw).toHaveTextContent('200'); // incoming_spo
    // on_order_po (120) shares the shared-supply columns.
    expect(brw).toHaveTextContent('80'); // reorder_level
  });

  it('shows a no-level dash rather than 0 when nobody has set a reorder level here', () => {
    const data: OrderSummaryLocations = {
      ...BLUE_LOCATIONS,
      locations: BLUE_LOCATIONS.locations.map((l) =>
        l.warehouse_code === 'JB' ? { ...l, reorder_level: null } : l,
      ),
    };
    renderPopover(state({ data }));
    openPopover();
    const rows = screen.getByTestId('location-rows');
    const jb = within(rows).getByText('JB').closest('tr') as HTMLElement;
    expect(within(jb).getByTitle('No level set here')).toBeInTheDocument();
  });

  it('shows the chosen split per location (AC-F08)', () => {
    renderPopover(state({ data: BLUE_LOCATIONS }));
    openPopover();
    const rows = screen.getByTestId('location-rows');
    const brw = within(rows).getByText('BRW').closest('tr') as HTMLElement;
    const jb = within(rows).getByText('JB').closest('tr') as HTMLElement;
    expect(brw).toHaveTextContent('400');
    expect(jb).toHaveTextContent('200');
  });

  it('restates the once-rounded product figure beside the split (AC-F11 / AC-F12)', () => {
    renderPopover(state({ data: BLUE_LOCATIONS }));
    openPopover();
    expect(screen.getByText(/Suggested once at the product/)).toHaveTextContent('300');
  });

  it('restates the chosen quantity, so the split can be checked against it', () => {
    renderPopover(state({ data: BLUE_LOCATIONS }));
    openPopover();
    expect(screen.getByText(/^Chosen:/)).toHaveTextContent('600');
  });

  it('says no quantity is chosen yet instead of a blank figure', () => {
    const data: OrderSummaryLocations = { ...BLUE_LOCATIONS, chosen_qty: null };
    renderPopover(state({ data }));
    openPopover();
    expect(screen.getByText('No quantity chosen yet')).toBeInTheDocument();
  });

  it('shows the badge count of member locations', () => {
    renderPopover(state({ data: BLUE_LOCATIONS }));
    openPopover();
    expect(screen.getByText('2 locations')).toBeInTheDocument();
  });
});

describe('ProductLocationsPopover - legacy presentation (AC-F10)', () => {
  const LEGACY_LOCATIONS: OrderSummaryLocations = {
    product_code: 'B2155-NL-BLUE',
    decision_grain: null,
    is_legacy: true,
    uom: 'PCS',
    uom_decimal_places: null,
    suggested_qty: 300,
    chosen_qty: 600,
    locations: [
      {
        warehouse_code: 'BRW',
        warehouse_name: 'Bandar Baru Warehouse',
        project_need: null,
        retail_need: null,
        on_hand: 60,
        incoming_spo: 200,
        on_order_po: 120,
        reorder_level: 80,
        avg_daily_demand: 2.1,
        allocated_qty: null,
      },
    ],
  };

  it('states the channel breakdown is unavailable on a legacy plan', () => {
    renderPopover(state({ data: LEGACY_LOCATIONS }));
    openPopover();
    expect(
      screen.getByText('This plan predates front planning, so its channel breakdown is unavailable.'),
    ).toBeInTheDocument();
  });

  it('renders each null channel cell as Unavailable, never as zero', () => {
    renderPopover(state({ data: LEGACY_LOCATIONS }));
    openPopover();
    const rows = screen.getByTestId('location-rows');
    const cells = within(rows).getAllByText('Unavailable');
    expect(cells).toHaveLength(2); // Project, Retail
  });

  it('does not render the legacy note on a front-planning run', () => {
    renderPopover(state({ data: BLUE_LOCATIONS }));
    openPopover();
    expect(
      screen.queryByText('This plan predates front planning, so its channel breakdown is unavailable.'),
    ).not.toBeInTheDocument();
  });
});


describe('ProductLocationsPopover - the header stays put (S4-04)', () => {
  it('the head sticks to the top of its own scroller, opaque and layered', () => {
    renderPopover(state({ data: BLUE_LOCATIONS }));
    openPopover();

    const scroller = screen.getByTestId('location-rows');
    // The scroller is the div, not a nested ScrollArea: nested, the inner one
    // became the head's offset parent and scrolled away carrying it.
    expect(scroller).toHaveClass('max-h-72');
    expect(scroller).toHaveClass('overflow-auto');
    expect(scroller.querySelector('[data-slot="scroll-area"]')).toBeNull();

    const head = scroller.querySelector('thead')!;
    expect(head).toHaveClass('sticky');
    expect(head).toHaveClass('top-0');
    // z-10 and an OPAQUE fill: `bg-muted/60` let forty rows of figures show
    // through the header as they passed under it.
    expect(head).toHaveClass('z-10');
    expect(head).toHaveClass('bg-popover');
    expect(head.className).not.toContain('bg-muted/60');
  });
});
