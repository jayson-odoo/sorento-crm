/**
 * DATE-PICKER-UNIFY slice B: RunPlanningModal date fields. Two range facts (Project delivery
 * range, Inquiries raised), each ONE typeable DateRangePicker, same payload as before.
 * Harness (mocks, renderModal, fixed clock) copied from RunPlanningModal.test.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}

type StubOption = { value: string; label: string; description?: string; searchText?: string };

// Stub the multi-select as a group of checkboxes so selection is deterministic. There
// are now TWO of them on this modal, so the group is labelled by its placeholder
// rather than a hard-coded name. Async mode (`fetchOptions`) is stubbed as well: a search
// box drives the fetch, exactly as the real component does after its debounce.
//
// `description` (V2, PLAN-reorder-plan-demand-class-orders) is rendered as a sibling text
// node beside the checkbox label - the Orders field's "N lines in range[, N awaiting ack]"
// caption.
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({
    value,
    onChange,
    options,
    fetchOptions,
    selectedOptions,
    placeholder,
    renderOption,
    renderTriggerLabel,
  }: {
    value: string[];
    onChange: (v: string[]) => void;
    options?: StubOption[];
    fetchOptions?: (query: string) => Promise<StubOption[]>;
    selectedOptions?: StubOption[];
    placeholder?: string;
    renderOption?: (opt: StubOption) => React.ReactNode;
    renderTriggerLabel?: (selected: StubOption[]) => React.ReactNode;
  }) => {
    const [fetched, setFetched] = React.useState<StubOption[]>([]);
    const [query, setQuery] = React.useState('');
    React.useEffect(() => {
      if (!fetchOptions) return;
      let live = true;
      void fetchOptions(query).then((rows) => {
        if (live) setFetched(rows);
      });
      return () => {
        live = false;
      };
    }, [fetchOptions, query]);
    const rows = fetchOptions ? fetched : (options ?? []);
    // The trigger's own closed-state label (D1: ONE line, "SO1, SO2 +12" rather than a
    // chip wall) - `chosen` is the same set the real component would pass, options
    // filtered to the current `value`. Built off `rows` UNFILTERED by the static
    // search box below, so a selection stays in the trigger label even while a query
    // narrows which rows are drawn - the real component keeps `chosen` off every
    // option it has ever seen, not just the currently visible page.
    const chosen = rows.filter((o) => value.includes(o.value));
    // Static mode (fix round 4 nit): a fuzzy-filter search box too, mirroring the real
    // component's own `opt.searchText ?? label` read (`SearchableMultiSelect.tsx` ~
    // L191) - so a static field (Orders, Warehouses) can be searched by a term that is
    // in `searchText` but never printed in `label`.
    const [staticQuery, setStaticQuery] = React.useState('');
    const visibleRows = fetchOptions
      ? rows
      : rows.filter((o) =>
          (o.searchText ?? o.label).toLowerCase().includes(staticQuery.toLowerCase()),
        );
    return (
      <div aria-label={placeholder ?? 'multi-select'}>
        {renderTriggerLabel ? (
          <div data-testid={`trigger-label-${placeholder}`}>{renderTriggerLabel(chosen)}</div>
        ) : null}
        {fetchOptions ? (
          <input
            aria-label={`Search ${placeholder ?? 'multi-select'}`}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        ) : (
          <input
            aria-label={`Search ${placeholder ?? 'multi-select'}`}
            value={staticQuery}
            onChange={(e) => setStaticQuery(e.target.value)}
          />
        )}
        {visibleRows.map((o) => (
          <label key={o.value}>
            <input
              type="checkbox"
              aria-label={o.label}
              checked={value.includes(o.value)}
              onChange={(e) =>
                onChange(
                  e.target.checked ? [...value, o.value] : value.filter((x) => x !== o.value),
                )
              }
            />
            {/* `data-testid` rather than a `getByText` string match: `renderOption` (real
                component) nests the description in its own <span>, and a match on
                `element.textContent` sidesteps guessing at that DOM shape. */}
            <span data-testid={`option-body-${o.value}`}>
              {renderOption ? (
                renderOption(o)
              ) : (
                <>
                  {o.label}
                  {o.description ? <span>{o.description}</span> : null}
                </>
              )}
            </span>
          </label>
        ))}
        {(selectedOptions ?? []).map((o) => (
          <span key={o.value} data-testid={`chip-${placeholder}`}>
            {o.label}
          </span>
        ))}
      </div>
    );
  },
}));

// The Demand field (V1-V4): a single SearchableSelect. Stubbed as a plain native <select>
// with a fixed test id - there is only ever ONE single-select on this modal, so the id does
// not need to route on whatever placeholder/label text the real field ends up using.
// `clearable` options are prepended with an empty-value row reading `placeholder` (mirrors
// the real component's "clear -> placeholder" reading), so a caller passing three explicit
// options (Project/Dealer/All) and a caller passing two options + `clearable` both render as
// the same three rows here.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
    clearable,
  }: {
    value: string;
    onChange: (v: string) => void;
    options: StubOption[];
    placeholder?: string;
    clearable?: boolean;
  }) => {
    const rows = clearable ? [{ value: '', label: placeholder ?? 'All' }, ...options] : options;
    return (
      <select
        data-testid="demand-select"
        aria-label={placeholder ?? 'Demand'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {rows.map((o) => (
          <option key={o.value || '__all__'} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    );
  },
}));

vi.mock('../../hooks/useScmOptions', () => ({
  useActiveWarehouseOptions: () => ({
    data: [
      { value: 'WH-KL', label: 'Kuala Lumpur DC' },
      { value: 'WH-JB', label: 'Johor Bahru DC' },
    ],
    isLoading: false,
    isError: false,
  }),
}));

/** The page the server answers with when nothing is typed. The two codes the R19 run could
 *  not pick are deliberately NOT in it - they only come back for a query. */
const FIRST_PAGE: StubOption[] = [
  { value: 'SRTWT7408', label: 'SRTWT7408 · Wall-hung WC 7408' },
  { value: 'SRTBS4832', label: 'SRTBS4832 · Basin mixer 4832' },
];
const OFF_FIRST_PAGE: StubOption[] = [
  { value: 'CB2907', label: 'CB2907 · Concealed cistern 2907' },
  { value: 'SRTWT7445-LV', label: 'SRTWT7445-LV · Wall-hung WC 7445 LV' },
];

const searchProductOptions = vi.fn(async (query: string): Promise<StubOption[]> => {
  const q = query.trim().toLowerCase();
  if (!q) return FIRST_PAGE;
  return [...FIRST_PAGE, ...OFF_FIRST_PAGE].filter((o) => o.label.toLowerCase().includes(q));
});

vi.mock('../../services/scmOptionsService', () => ({
  searchProductOptions: (query: string) => searchProductOptions(query),
}));

/** V1-V4 (PLAN-reorder-plan-demand-class-orders): the Orders field's candidates, keyed on
 *  the From/To range. `RunPlanningModal.tsx` calls
 *  `getCandidateOrders({ from: horizonStart || undefined, to: horizon || undefined })` -
 *  ONE object argument, `undefined` (not `''`) when a bound is unset.
 *
 *  `rows_raised_in_window` and the `raised_from`/`raised_to` range (AC-RF-1..8,
 *  `PLAN-reorder-plan-raised-filter.md`, 22 Sep 2026) ride the SAME call/object - a
 *  window typed into "Inquiries raised" From/To adds two more keys, never a second
 *  fetch. */
type CandidateOrder = {
  so_number: string;
  project_label: string;
  customer_name: string;
  rows_total: number;
  rows_in_range: number;
  rows_raised_in_window: number;
  rows_awaiting: number;
  first_delivery: string;
  last_delivery: string;
};
type CandidateOrdersRange = { from?: string; to?: string; raised_from?: string; raised_to?: string };
const getCandidateOrders = vi.fn(async (range: CandidateOrdersRange): Promise<CandidateOrder[]> => {
  // Ignored by this default implementation - kept as a named, typed parameter (not
  // `_range`) so callers below (`mockImplementation`) type-check against the same
  // one-argument signature `vi.mock` calls this with.
  void range;
  return [];
});
getCandidateOrders.mockResolvedValue([]);
vi.mock('../services/reorderRunService', () => ({
  getCandidateOrders: (range: CandidateOrdersRange) => getCandidateOrders(range),
}));

import { RunPlanningModal } from './RunPlanningModal';

async function renderModal(over: Partial<React.ComponentProps<typeof RunPlanningModal>> = {}) {
  const onSubmit = vi.fn();
  const onOpenChange = vi.fn();
  // The Orders field's candidate-orders fetch (V1-V4) goes through `useQuery`, which needs
  // a QueryClientProvider ancestor - a fresh client per render, retries off so a red (the
  // endpoint/mock not wired yet) surfaces immediately instead of retrying for seconds.
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <RunPlanningModal open onOpenChange={onOpenChange} onSubmit={onSubmit} isSubmitting={false} {...over} />
    </QueryClientProvider>,
  );
  // Wait out the products field's first server search, so nothing resolves after the test.
  await screen.findByLabelText(FIRST_PAGE[0].label);
  return { onSubmit, onOpenChange };
}

// Fixed clock. The modal refuses a To cut-off before today (B2, `submit()` in
// RunPlanningModal.tsx), and the scenarios below type literal 2026 dates (2026-10-31,
// 2026-12-31). On the real clock those turned past on 1 Nov 2026 and V2/V4 failed the
// release. Only `Date` is faked, so `waitFor` and `setTimeout` keep running for real.
// 15 Jul 2026, local noon: before every To date the file uses as a valid cut-off.
const FIXED_NOW = new Date(2026, 6, 15, 12, 0, 0);

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(FIXED_NOW);
});

afterEach(() => {
  vi.useRealTimers();
});

const RANGE_PH = 'DD/MM/YYYY - DD/MM/YYYY';

function typeRange(el: HTMLElement, text: string) {
  fireEvent.change(el, { target: { value: text } });
  fireEvent.keyDown(el, { key: 'Enter' });
}

describe('RunPlanningModal - dates (DATE-PICKER-UNIFY slice B)', () => {
  it('AC1: no native date input; the delivery range is one typeable range field', async () => {
    await renderModal();
    expect(document.body.querySelector('input[type="date"]')).toBeNull();
    expect(screen.getAllByPlaceholderText(RANGE_PH)).toHaveLength(1);
  });

  it('AC2/AC9: typing a delivery range sends the same plan_horizon_start / plan_horizon_date', async () => {
    const { onSubmit } = await renderModal();
    typeRange(screen.getAllByPlaceholderText(RANGE_PH)[0], '01/11/2026 - 30/11/2026');
    fireEvent.click(screen.getByRole('button', { name: 'Start Plan' }));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ plan_horizon_start: '2026-11-01', plan_horizon_date: '2026-11-30' }),
    );
  });

  it('AC9: the typed delivery range still drives the candidate-orders call with from/to', async () => {
    await renderModal();
    typeRange(screen.getAllByPlaceholderText(RANGE_PH)[0], '01/08/2026 - 31/10/2026');
    fireEvent.change(screen.getByTestId('demand-select'), { target: { value: 'project' } });
    await waitFor(() =>
      expect(getCandidateOrders).toHaveBeenCalledWith(
        expect.objectContaining({ from: '2026-08-01', to: '2026-10-31' }),
      ),
    );
  });

  it('AC2/AC9: Inquiries raised (Project) is a second range field sending raised_from / raised_to', async () => {
    await renderModal();
    fireEvent.change(screen.getByTestId('demand-select'), { target: { value: 'project' } });
    await waitFor(() => expect(screen.getAllByPlaceholderText(RANGE_PH)).toHaveLength(2));
    expect(document.body.querySelector('input[type="date"]')).toBeNull();
    typeRange(screen.getAllByPlaceholderText(RANGE_PH)[1], '17/09/2026 - 18/09/2026');
    await waitFor(() =>
      expect(getCandidateOrders).toHaveBeenCalledWith(
        expect.objectContaining({ raised_from: '2026-09-17', raised_to: '2026-09-18' }),
      ),
    );
  });
});
