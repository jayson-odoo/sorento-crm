/**
 * SCM S4 - PoWorklistView (UAC Group E2).
 *
 * What these pin is the difference between a worklist and a second decision point, and
 * the states a fabricated fixture would never contain:
 *
 * - **No Accept, no Reject, no quantity field.** Joey executes; Mr Loo decided. A
 *     control here that changed the decision would make the two screens disagree about
 *     what was ordered.
 * - **A decision to buy nothing is a ROW** (AC-E2.5) saying no PO is needed. Absent, it
 *     is indistinguishable from a decision nobody made.
 * - **The not-keyed filter is the default** (AC-E2.4), because that is the screen's
 *     primary use.
 * - **A missing date is named, never filled in.** Most of the real book has no dated
 *     shortfall, and a place-by date derived from a guessed lead time would be acted on.
 * - **The late flag is on the row**, not left for the reader to compute from two dates.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

const mockUsePoWorklist = vi.fn();
const mockMutate = vi.fn();

vi.mock('../hooks/usePoWorklist', () => ({
  usePoWorklist: (...args: unknown[]) => mockUsePoWorklist(...args),
  useSetKeyedStatus: () => ({ mutate: mockMutate, isPending: false }),
  poWorklistKey: () => ['scm', 'reorder', 'po-worklist', null],
}));

vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/reorder',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

// The listing personalization hook fetches through react-query, and the grid renders no
// rows without it mocked. The "DataGrid does not render rows in jsdom" belief was this
// unmocked fetch, not a limitation of the grid.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

import { PoWorklistView } from './PoWorklistView';
import type { PoWorklistRow } from '../types/poWorklist.types';

function row(over: Partial<PoWorklistRow> = {}): PoWorklistRow {
  return {
    product_code: 'SRTWC8613-RL',
    product_name: 'Wall hung WC, rimless',
    uom: 'UNIT',
    chosen_qty: 224,
    suggested_qty: 224,
    chosen_supplier_code: 'FOSHAN-CF',
    chosen_supplier_name: 'Foshan Ceramic Fixtures Co Ltd',
    decided_by: 'Mr Loo',
    decided_at: '2026-08-04T09:14:00',
    need_by: '2026-10-13',
    place_by: '2026-08-29',
    lead_time_days: 45,
    is_late: false,
    last_po_cost: 1011,
    last_po_currency: 'MYR',
    cash_committed: 226464,
    keyed_status: 'not_keyed',
    keyed_by: null,
    keyed_at: null,
    ...over,
  };
}

function state(over: Record<string, unknown> = {}) {
  return {
    data: {
      run_id: 'run-2026-w32',
      as_of: '2026-08-04',
      decision_grain: 'product',
      front_planning_contract_version: 1,
      rows: [row()],
    },
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...over,
  };
}

function renderView(s: Record<string, unknown>, onBack?: () => void) {
  mockUsePoWorklist.mockReturnValue(s);
  return render(<PoWorklistView runId="run-2026-w32" onBack={onBack} />);
}

function rowFor(code: string) {
  const cell = screen.getByTitle(code);
  const tr = cell.closest('tr');
  if (!tr) throw new Error(`no row for ${code}`);
  return tr as HTMLElement;
}

beforeEach(() => {
  mockUsePoWorklist.mockReset();
  mockMutate.mockReset();
});

describe('PoWorklistView - it is a worklist, not a decision', () => {
  it('offers no Accept, Reject or quantity control', () => {
    renderView(state());
    expect(screen.queryByRole('button', { name: /accept/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /reject/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();
  });

  it('shows what was decided, by whom, with the engine figure beside it (AC-E2.1)', () => {
    renderView(state());
    const r = rowFor('SRTWC8613-RL');
    expect(r).toHaveTextContent('224');
    expect(r).toHaveTextContent('Foshan Ceramic Fixtures Co Ltd');
    expect(r).toHaveTextContent('Mr Loo');
  });

  it('says where to go to change a decision rather than offering to change it here', () => {
    renderView(state());
    expect(screen.getByText(/go back\s+to the order summary/i)).toBeInTheDocument();
  });
});

describe('PoWorklistView - committed cash reads like money everywhere else (AC-2.2)', () => {
  it('writes a ringgit total with the same glyph the rest of the screens use', () => {
    // It used to print the raw code (`MYR 226,464`), which is the plan screen writing
    // money a second way.
    renderView(state());
    const r = rowFor('SRTWC8613-RL');
    expect(within(r).getByText('RM 226,464.00')).toBeInTheDocument();
  });

  it('names a foreign currency rather than claiming ringgit', () => {
    renderView(
      state({
        data: {
          run_id: 'run-2026-w32',
          as_of: '2026-08-04',
          rows: [row({ last_po_currency: 'USD', cash_committed: 226464 })],
        },
      }),
    );
    const r = rowFor('SRTWC8613-RL');
    expect(within(r).getByText('USD 226,464.00')).toBeInTheDocument();
  });

  it('keeps the cents, on a column somebody totals by eye', () => {
    // qty x unit cost lands on cents far more often than not, and a rounded column does
    // not add up to the figure beside it.
    renderView(
      state({
        data: {
          run_id: 'run-2026-w32',
          as_of: '2026-08-04',
          rows: [row({ cash_committed: 226464.5 })],
        },
      }),
    );
    const r = rowFor('SRTWC8613-RL');
    expect(within(r).getByText('RM 226,464.50')).toBeInTheDocument();
  });

  it('reads a cost with no currency on file as ringgit, not as "no cost recorded"', () => {
    // The row guard used to treat a missing currency as a missing cost. Under the shared
    // formatter a blank currency means base, so a real committed figure was being hidden
    // behind "no cost recorded" - the one thing this column exists to show.
    renderView(
      state({
        data: {
          run_id: 'run-2026-w32',
          as_of: '2026-08-04',
          rows: [row({ cash_committed: 226464.5, last_po_currency: null })],
        },
      }),
    );
    const r = rowFor('SRTWC8613-RL');
    expect(within(r).getByText('RM 226,464.50')).toBeInTheDocument();
    expect(within(r).queryByText('no cost recorded')).not.toBeInTheDocument();
  });

  it('says no cost is recorded rather than printing a zero', () => {
    renderView(
      state({
        data: {
          run_id: 'run-2026-w32',
          as_of: '2026-08-04',
          rows: [row({ cash_committed: null, last_po_cost: null, last_po_currency: null })],
        },
      }),
    );
    const r = rowFor('SRTWC8613-RL');
    expect(within(r).getByText('no cost recorded')).toBeInTheDocument();
  });
});

describe('PoWorklistView - the use-pool decision (AC-E2.5)', () => {
  it('renders a zero-quantity decision as a row saying no PO is needed', () => {
    renderView(
      state({
        data: {
          run_id: 'run-2026-w32',
          as_of: '2026-08-04',
          rows: [
            row({
              product_code: 'SRTWT7408',
              chosen_qty: 0,
              suggested_qty: 67,
              chosen_supplier_code: null,
              chosen_supplier_name: null,
              cash_committed: null,
              last_po_cost: null,
              last_po_currency: null,
            }),
          ],
        },
      }),
    );
    // Not outstanding work, so the default filter hides it. Widened here because what is
    // under test is how the ROW renders, not which filter shows it.
    fireEvent.click(document.getElementById('keyed-status-filter')!);
    fireEvent.click(screen.getByText('All statuses'));
    const r = rowFor('SRTWT7408');
    expect(within(r).getByText('No PO needed')).toBeInTheDocument();
    // Nothing to key, so no control that would record a fiction.
    expect(within(r).getByText('nothing to key')).toBeInTheDocument();
    expect(within(r).queryByRole('combobox')).not.toBeInTheDocument();
  });
});

describe('PoWorklistView - dates and the late flag (AC-C2)', () => {
  it('names a missing need-by date instead of leaving the cell blank', () => {
    renderView(
      state({
        data: {
          run_id: 'r',
          as_of: '2026-08-04',
          rows: [row({ need_by: null, place_by: null })],
        },
      }),
    );
    expect(screen.getByText('no dated shortfall')).toBeInTheDocument();
  });

  it('says the lead time is missing rather than deriving a place-by date from a guess', () => {
    renderView(
      state({
        data: {
          run_id: 'r',
          as_of: '2026-08-04',
          rows: [row({ need_by: '2026-09-03', place_by: null, lead_time_days: null })],
        },
      }),
    );
    expect(screen.getByText('no lead time')).toBeInTheDocument();
  });

  it('flags a place-by date that has passed', () => {
    renderView(
      state({
        data: {
          run_id: 'r',
          as_of: '2026-08-04',
          rows: [row({ place_by: '2026-06-27', is_late: true })],
        },
      }),
    );
    expect(screen.getByText('late')).toBeInTheDocument();
  });

  it('does not flag a place-by date still in the future', () => {
    renderView(state());
    expect(screen.queryByText('late')).not.toBeInTheDocument();
  });
});

describe('PoWorklistView - the keyed status (AC-E2.2 / E2.3 / E2.4)', () => {
  it('defaults to what is still to key, and that INCLUDES a row mid-keying', () => {
    // "Still to key" is what AC-E2.4 is actually asking for. A row somebody is part-way
    // through is still left to do, and on a shared queue it is the row you most want to
    // see: it is how the second person knows not to start it. Excluding it also made the
    // tile (which counts everything not keyed) contradict the list one line below it.
    renderView(
      state({
        data: {
          run_id: 'r',
          as_of: '2026-08-04',
          rows: [
            row({ product_code: 'A-NOT', keyed_status: 'not_keyed' }),
            row({ product_code: 'B-MID', keyed_status: 'keying', keyed_by: 'Joey' }),
            row({ product_code: 'C-DONE', keyed_status: 'keyed', keyed_by: 'Joey' }),
          ],
        },
      }),
    );
    expect(screen.getByTitle('A-NOT')).toBeInTheDocument();
    expect(screen.getByTitle('B-MID')).toBeInTheDocument();
    expect(screen.queryByTitle('C-DONE')).not.toBeInTheDocument();
  });

  it('leaves a use-pool row out of the outstanding work but keeps it in the list', () => {
    // It carries no purchase order, so it is not work; it still has to be reachable, or
    // the worklist cannot be reconciled against the decisions (AC-E2.5).
    renderView(
      state({
        data: {
          run_id: 'r',
          as_of: '2026-08-04',
          rows: [row({ product_code: 'B-POOL', chosen_qty: 0, keyed_status: 'not_keyed' })],
        },
      }),
    );
    expect(screen.queryByTitle('B-POOL')).not.toBeInTheDocument();
    expect(screen.getByText(/0 of 1 still to key/)).toBeInTheDocument();
  });

  it('writes the new status with the run it belongs to', () => {
    renderView(state());
    // Found THROUGH the row, so the toolbar's own status filter cannot match instead.
    const r = rowFor('SRTWC8613-RL');
    const rowSelect = within(r).getByRole('combobox');
    fireEvent.click(rowSelect);
    const option = screen.getByText('Keyed');
    fireEvent.click(option);
    expect(mockMutate).toHaveBeenCalledWith({
      productCode: 'SRTWC8613-RL',
      input: { run_id: 'run-2026-w32', keyed_status: 'keyed' },
    });
  });

  it('keys a location-grain row on its own location, and gives each location its own control', () => {
    // One product decided at two locations is two purchase orders. Keying one must post
    // that location, and the two selects cannot share a DOM id.
    renderView(
      state({
        data: {
          run_id: 'run-2026-w32',
          as_of: '2026-08-04',
          decision_grain: 'location',
          front_planning_contract_version: 1,
          rows: [
            row({ warehouse_code: 'WH-A', warehouse_name: 'Warehouse A', location_allocations: null }),
            row({ warehouse_code: 'WH-B', warehouse_name: 'Warehouse B', location_allocations: null }),
          ],
        },
      }),
    );
    const a = document.getElementById('keyed-status-SRTWC8613-RL-WH-A');
    const b = document.getElementById('keyed-status-SRTWC8613-RL-WH-B');
    expect(a).toBeInTheDocument();
    expect(b).toBeInTheDocument();
    expect(a).not.toBe(b);
    expect(document.getElementById('keyed-status-SRTWC8613-RL')).toBeNull();

    fireEvent.click(b!);
    fireEvent.click(screen.getByText('Keyed'));
    expect(mockMutate).toHaveBeenCalledTimes(1);
    expect(mockMutate).toHaveBeenCalledWith({
      productCode: 'SRTWC8613-RL',
      input: { run_id: 'run-2026-w32', keyed_status: 'keyed', warehouse_code: 'WH-B' },
    });
  });

  it('posts no location for a product-grain row', () => {
    renderView(state());
    const r = rowFor('SRTWC8613-RL');
    fireEvent.click(within(r).getByRole('combobox'));
    fireEvent.click(screen.getByText('Keyed'));
    const [{ input }] = mockMutate.mock.calls[0] as [{ input: Record<string, unknown> }];
    expect('warehouse_code' in input).toBe(false);
  });

  it('names who set the status and when, once it has been set', () => {
    renderView(
      state({
        data: {
          run_id: 'r',
          as_of: '2026-08-04',
          rows: [
            row({ keyed_status: 'keying', keyed_by: 'Joey', keyed_at: '2026-08-04T11:15:00' }),
          ],
        },
      }),
    );
    // Through the row: "Keying" also appears in the toolbar filter's own option list.
    const r = rowFor('SRTWC8613-RL');
    expect(within(r).getByText(/Joey/)).toBeInTheDocument();
  });
});

describe('PoWorklistView - the grain chip reads the run, never infers it', () => {
  it('says legacy when the contract version is null, even with a grain stamped', () => {
    // `lib/planGrain.ts`: a legacy run is identified by its NULL contract version. The
    // planning view says "Legacy run" for this run, and this chip has to agree with it.
    renderView(
      state({
        data: {
          run_id: 'run-legacy',
          as_of: '2026-08-04',
          decision_grain: 'product',
          front_planning_contract_version: null,
          rows: [row()],
        },
      }),
    );
    expect(screen.getByTestId('worklist-grain-chip')).toHaveTextContent('Legacy run');
  });

  it('names the grain on a front-planning run', () => {
    renderView(
      state({
        data: {
          run_id: 'run-2026-w32',
          as_of: '2026-08-04',
          decision_grain: 'location',
          front_planning_contract_version: 1,
          rows: [row({ warehouse_code: 'WH-A', warehouse_name: 'Warehouse A' })],
        },
      }),
    );
    expect(screen.getByTestId('worklist-grain-chip')).toHaveTextContent('Plan grain: Location');
  });
});

describe('PoWorklistView - the states around the data', () => {
  it('renders a skeleton while loading', () => {
    renderView(state({ isLoading: true, data: undefined }));
    expect(screen.getByTestId('po-worklist-loading')).toBeInTheDocument();
  });

  it('renders the extracted message and a retry on failure', () => {
    const refetch = vi.fn();
    renderView(
      state({ isError: true, error: new Error('No completed plan yet'), data: undefined, refetch }),
    );
    expect(screen.getByText('No completed plan yet')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /try again/i }));
    expect(refetch).toHaveBeenCalled();
  });

  it('says nothing has been decided rather than showing an empty grid', () => {
    renderView(state({ data: { run_id: 'r', as_of: null, rows: [] } }));
    expect(screen.getByText('No decisions to key yet.')).toBeInTheDocument();
  });

  it('counts only real purchase orders as left to key, never a use-pool row', () => {
    renderView(
      state({
        data: {
          run_id: 'r',
          as_of: '2026-08-04',
          rows: [
            row({ product_code: 'A-BUY', chosen_qty: 10, keyed_status: 'not_keyed' }),
            row({ product_code: 'B-POOL', chosen_qty: 0, keyed_status: 'not_keyed' }),
          ],
        },
      }),
    );
    // Two rows, one of which needs no PO at all, so only ONE is left to key.
    expect(screen.getByText(/1 of 2 still to key/)).toBeInTheDocument();
  });
});

describe('PoWorklistView - onBack (this report has no row in the buy grid to return to)', () => {
  it('renders no back link when the caller supplies none', () => {
    renderView(state());
    expect(screen.queryByText('Back to plan')).not.toBeInTheDocument();
  });

  it('calls onBack when "Back to plan" is clicked, with data on screen', () => {
    const onBack = vi.fn();
    renderView(state(), onBack);
    screen.getByText('Back to plan').click();
    expect(onBack).toHaveBeenCalled();
  });

  it('still offers a way back on the error state', () => {
    const onBack = vi.fn();
    renderView(state({ isError: true, error: new Error('boom'), data: undefined }), onBack);
    screen.getByText('Back to plan').click();
    expect(onBack).toHaveBeenCalled();
  });

  it('still offers a way back on the empty state', () => {
    const onBack = vi.fn();
    renderView(state({ data: { run_id: 'r', as_of: null, rows: [] } }), onBack);
    screen.getByText('Back to plan').click();
    expect(onBack).toHaveBeenCalled();
  });
});
