/**
 * Start Plan (plan 4.2, UAC B1/B2). Fields in the order the buyer decides them - Sales
 * order cut-off, Warehouses, Products - all optional, all "empty means everything". There
 * is NO Select all (empty already means every warehouse), no cash budget field (captain,
 * 20 Aug: budget is a backend/post-run capability), no market-insight toggle and no legacy
 * `buy_scope`. Submit emits an unchanged { warehouse_codes, product_codes,
 * plan_horizon_date }.
 *
 * Products are SEARCHED ON THE SERVER (R19 browser run: the old capped 100-row list could
 * not offer CB2907 or SRTWT7445-LV). The multi-select and the warehouse hook are stubbed so
 * the pick is deterministic; `searchProductOptions` is stubbed as a paged endpoint whose
 * first page deliberately does NOT contain those two codes.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}

type StubOption = { value: string; label: string; description?: string };

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
    // filtered to the current `value`.
    const chosen = rows.filter((o) => value.includes(o.value));
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
        ) : null}
        {rows.map((o) => (
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
  useWarehouseOptions: () => ({
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

beforeEach(() => vi.clearAllMocks());

describe('RunPlanningModal - Start Plan (plan 4.2)', () => {
  it('shows the three inputs, and no cash budget, market toggle or buy_scope', async () => {
    await renderModal();
    // The title and the submit button both read "Start Plan" - that is the point.
    expect(screen.getAllByText('Start Plan').length).toBeGreaterThan(0);
    // Renamed by Lane D (AC-D1b, `PLAN-order-sheet-oi-reports-22sep.md`) - see the
    // "Lane D" describe block below for the section's new label.
    expect(screen.getByText('Project delivery range')).toBeInTheDocument();
    expect(screen.getByText('Warehouses')).toBeInTheDocument();
    expect(screen.getByLabelText('All warehouses')).toBeInTheDocument();
    expect(screen.getByText('Products')).toBeInTheDocument();
    expect(screen.getByLabelText('All products')).toBeInTheDocument();
    // No cash budget field (captain, 20 Aug), no market insight toggle and no
    // buy-scope (network/warehouse) selector.
    expect(screen.queryByLabelText(/Cash budget/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/market/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/buy scope/i)).not.toBeInTheDocument();
  });

  it('B1: fields read top to bottom Project delivery range, Warehouses, Products', async () => {
    await renderModal();
    // The dialog renders through a portal, so the labels are on `document.body`.
    // Renamed by Lane D (AC-D1b) - see below.
    const labels = Array.from(document.body.querySelectorAll('label, [data-slot="label"]'))
      .map((el) => el.textContent?.trim())
      .filter((t): t is string =>
        t === 'Project delivery range' || t === 'Warehouses' || t === 'Products',
      );
    expect(labels).toEqual(['Project delivery range', 'Warehouses', 'Products']);
  });

  it('B1: has no Select all - empty already means every warehouse', async () => {
    await renderModal();
    expect(screen.queryByRole('button', { name: /Select all/i })).not.toBeInTheDocument();
  });

  it('B1: the buttons are Cancel and Start Plan', async () => {
    await renderModal();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Start Plan' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Generate plan/i })).not.toBeInTheDocument();
  });

  it('submits with NO warehouse picked: empty means every warehouse (P1)', async () => {
    const { onSubmit } = await renderModal();
    fireEvent.click(screen.getByRole('button', { name: 'Start Plan' }));
    expect(onSubmit).toHaveBeenCalledWith({
      warehouse_codes: [],
      product_codes: [],
      plan_horizon_start: '',
      plan_horizon_date: '',
    });
    expect(screen.queryByText(/Select at least one warehouse/i)).not.toBeInTheDocument();
    expect(screen.getByText('Leave empty to plan every warehouse.')).toBeInTheDocument();
  });

  it('emits { warehouse_codes, product_codes, plan_horizon_date } on submit (M8-D5 / AC-B8a)', async () => {
    const { onSubmit } = await renderModal();
    fireEvent.click(screen.getByLabelText('Johor Bahru DC'));
    fireEvent.click(screen.getByRole('button', { name: 'Start Plan' }));
    expect(onSubmit).toHaveBeenCalledWith({
      warehouse_codes: ['WH-JB'],
      product_codes: [],
      plan_horizon_start: '',
      plan_horizon_date: '',
    });
  });

  it('Clear all empties a warehouse pick', async () => {
    const { onSubmit } = await renderModal();
    fireEvent.click(screen.getByLabelText('Johor Bahru DC'));
    fireEvent.click(screen.getByRole('button', { name: /Clear all/i }));
    fireEvent.click(screen.getByRole('button', { name: 'Start Plan' }));
    expect(onSubmit).toHaveBeenCalledWith({
      warehouse_codes: [],
      product_codes: [],
      plan_horizon_start: '',
      plan_horizon_date: '',
    });
  });

  it('narrows the run to the picked products, by human code (AC-B8a)', async () => {
    const { onSubmit } = await renderModal();
    fireEvent.click(screen.getByLabelText('Kuala Lumpur DC'));
    fireEvent.click(screen.getByLabelText('SRTWT7408 · Wall-hung WC 7408'));
    fireEvent.click(screen.getByRole('button', { name: 'Start Plan' }));
    expect(onSubmit).toHaveBeenCalledWith({
      warehouse_codes: ['WH-KL'],
      product_codes: ['SRTWT7408'],
      plan_horizon_start: '',
      plan_horizon_date: '',
    });
  });

  it('does NOT require a product: empty means every product, so the run stays as it was', async () => {
    await renderModal();
    // No "Clear all" for products until something is picked, and no validation error
    // when none ever is.
    fireEvent.click(screen.getByLabelText('Kuala Lumpur DC'));
    fireEvent.click(screen.getByRole('button', { name: 'Start Plan' }));
    expect(screen.queryByText(/Select at least one product/i)).not.toBeInTheDocument();
    expect(screen.getByText('Leave empty to plan every product.')).toBeInTheDocument();
  });

  describe('Products are searched on the server, so the catalogue is not capped (R19)', () => {
    it('asks the server for the first page with no query when the field opens', async () => {
      await renderModal();
      expect(searchProductOptions).toHaveBeenCalledWith('');
    });

    it('typing sends the query to the server rather than filtering the loaded page', async () => {
      await renderModal();
      fireEvent.change(screen.getByLabelText('Search All products'), {
        target: { value: 'CB2907' },
      });
      await waitFor(() => expect(searchProductOptions).toHaveBeenCalledWith('CB2907'));
    });

    it('a product outside the first page is selectable and its code is what submit sends', async () => {
      const { onSubmit } = await renderModal();
      // Not on the first page - the capped list this replaced could never offer it.
      expect(screen.queryByLabelText(/CB2907/)).not.toBeInTheDocument();

      fireEvent.change(screen.getByLabelText('Search All products'), {
        target: { value: 'CB2907' },
      });
      fireEvent.click(await screen.findByLabelText('CB2907 · Concealed cistern 2907'));
      fireEvent.click(screen.getByRole('button', { name: 'Start Plan' }));

      expect(onSubmit).toHaveBeenCalledWith({
        warehouse_codes: [],
        product_codes: ['CB2907'],
        plan_horizon_start: '',
        plan_horizon_date: '',
      });
    });

    it('keeps a picked product as a named chip once the search moves on to another page', async () => {
      await renderModal();
      fireEvent.change(screen.getByLabelText('Search All products'), {
        target: { value: 'SRTWT7445-LV' },
      });
      fireEvent.click(await screen.findByLabelText('SRTWT7445-LV · Wall-hung WC 7445 LV'));

      // Search on to a page that does not contain it: the chip still reads as the product,
      // not as a bare code.
      fireEvent.change(screen.getByLabelText('Search All products'), {
        target: { value: 'Basin' },
      });
      await waitFor(() => expect(searchProductOptions).toHaveBeenCalledWith('Basin'));
      expect(
        screen.getByTestId('chip-All products').textContent,
      ).toBe('SRTWT7445-LV · Wall-hung WC 7445 LV');
    });
  });

  describe('Sales orders needed - To (B2: a past date silently plans zero demand)', () => {
    it('sets the date input\'s own min to today, so the picker cannot offer the past', async () => {
      await renderModal();
      const input = screen.getByLabelText('To') as HTMLInputElement;
      // Local calendar date, matching the component's own `todayDateInputValue()` - never
      // `toISOString()`'s UTC one, which can read a day off near midnight.
      const now = new Date();
      const today = [
        now.getFullYear(),
        String(now.getMonth() + 1).padStart(2, '0'),
        String(now.getDate()).padStart(2, '0'),
      ].join('-');
      expect(input.min).toBe(today);
    });

    it('blocks submit with a past cutoff and explains why, even if typed past the min', async () => {
      const { onSubmit } = await renderModal();
      fireEvent.click(screen.getByLabelText('Kuala Lumpur DC'));
      fireEvent.change(screen.getByLabelText('To'), { target: { value: '2000-01-01' } });
      fireEvent.click(screen.getByRole('button', { name: 'Start Plan' }));

      expect(onSubmit).not.toHaveBeenCalled();
      expect(screen.getByText(/cut-off cannot be in the past/i)).toBeInTheDocument();
    });

    it('accepts today and a future date', async () => {
      const { onSubmit } = await renderModal();
      fireEvent.click(screen.getByLabelText('Kuala Lumpur DC'));
      fireEvent.change(screen.getByLabelText('To'), { target: { value: '2099-12-31' } });
      fireEvent.click(screen.getByRole('button', { name: 'Start Plan' }));

      expect(onSubmit).toHaveBeenCalledWith({
        warehouse_codes: ['WH-KL'],
        product_codes: [],
        plan_horizon_start: '',
        plan_horizon_date: '2099-12-31',
      });
    });
  });

  // ===========================================================================
  // S4 (reorder-feedback-9sep.md, AC-S4.4) - the window gains a START date, under a
  // renamed "Sales orders needed" section with From/To inputs, both optional.
  // ===========================================================================

  describe('Sales orders needed - From/To window (AC-S4.4)', () => {
    it('shows the section (relabelled "Project delivery range" by Lane D/AC-D1b) with separate From and To date inputs', async () => {
      await renderModal();
      expect(screen.getByText('Project delivery range')).toBeInTheDocument();
      expect(screen.getByLabelText('From')).toBeInTheDocument();
      expect(screen.getByLabelText('To')).toBeInTheDocument();
    });

    it('the helper text reads "Empty = every open order counts."', async () => {
      await renderModal();
      expect(screen.getByText('Empty = every open order counts.')).toBeInTheDocument();
    });

    it('both are optional: submitting with neither set still works', async () => {
      const { onSubmit } = await renderModal();
      fireEvent.click(screen.getByRole('button', { name: 'Start Plan' }));
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({ plan_horizon_start: '', plan_horizon_date: '' }),
      );
    });

    it('To before From is refused inline and blocks submit', async () => {
      const { onSubmit } = await renderModal();
      fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-06-01' } });
      fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-01-01' } });
      fireEvent.click(screen.getByRole('button', { name: 'Start Plan' }));

      expect(onSubmit).not.toHaveBeenCalled();
      expect(screen.getByText(/to.*before.*from|from.*after.*to/i)).toBeInTheDocument();
    });

    it('submits both dates in ManualPlanInputs when both are set', async () => {
      const { onSubmit } = await renderModal();
      fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-01-01' } });
      fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-12-31' } });
      fireEvent.click(screen.getByRole('button', { name: 'Start Plan' }));

      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          plan_horizon_start: '2026-01-01',
          plan_horizon_date: '2026-12-31',
        }),
      );
    });
  });

  // ===========================================================================
  // V1-V4 (PLAN-reorder-plan-demand-class-orders, UAC J1-J3) - Demand = Project / Dealer /
  // All, gating a new Orders picker sourced from `getCandidateOrders({ from, to })`.
  // ===========================================================================

  describe('Demand scope - Project / Dealer / All (V1-V4)', () => {
    it('V1: Demand defaults to All; Orders is present for All and Project, absent for Dealer (Lane D, AC-D1/AC-D6)', async () => {
      await renderModal();
      expect(await screen.findByText('Orders')).toBeInTheDocument();

      fireEvent.change(screen.getByTestId('demand-select'), { target: { value: 'project' } });
      expect(await screen.findByText('Orders')).toBeInTheDocument();

      fireEvent.change(screen.getByTestId('demand-select'), { target: { value: 'retail' } });
      await waitFor(() => expect(screen.queryByText('Orders')).not.toBeInTheDocument());
    });

    it('V2: Project options come from getCandidateOrders({from,to}); rows_in_range>0 is pre-selected; label + description', async () => {
      // `mockResolvedValue` (persistent), not `...Once`: Lane D (AC-D1) now fetches
      // candidates as soon as the modal opens (Demand = All, the default), so this
      // scenario's From/To edits each trigger their OWN intervening fetch before the
      // one this test cares about - a `...Once` queued for exactly one call would land
      // on the wrong one.
      getCandidateOrders.mockResolvedValue([
        {
          so_number: 'SO419517',
          project_label: 'OTM GROUP / TAT LIAN',
          customer_name: 'OTM',
          rows_total: 7,
          rows_raised_in_window: 7,
          rows_in_range: 7,
          rows_awaiting: 2,
          first_delivery: '2026-08-01',
          last_delivery: '2026-10-01',
        },
        {
          so_number: 'SO420374',
          project_label: 'ARC RESIDENCE',
          customer_name: 'ARC',
          rows_total: 3,
          rows_raised_in_window: 3,
          rows_in_range: 0,
          rows_awaiting: 0,
          first_delivery: '2026-11-02',
          last_delivery: '2027-01-04',
        },
      ]);
      const { onSubmit } = await renderModal();
      fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-08-01' } });
      fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-10-31' } });
      fireEvent.change(screen.getByTestId('demand-select'), { target: { value: 'project' } });

      await waitFor(() =>
        expect(getCandidateOrders).toHaveBeenCalledWith({ from: '2026-08-01', to: '2026-10-31' }),
      );

      // Fix round 3 item 3: the option's accessible name (label) and the menu row's own
      // printed text now agree - both "<SO number> - <customer_name>", `project_label`
      // dropped from the label.
      expect(
        await screen.findByLabelText('SO419517 - OTM'),
      ).toBeInTheDocument();
      // Owner ruling (Lane D fix round 1): one-line menu rows under Project too -
      // "<SO number> - <customer>", the awaiting-ack count appended only when non-zero.
      expect(screen.getByTestId('option-body-SO419517').textContent).toBe(
        'SO419517 - OTM, 2 awaiting ack',
      );
      expect(screen.getByTestId('option-body-SO420374').textContent).toBe('SO420374 - ARC');

      // Pre-selected: only the SO with rows_in_range > 0.
      expect(
        (screen.getByLabelText('SO419517 - OTM') as HTMLInputElement).checked,
      ).toBe(true);
      expect(
        (screen.getByLabelText('SO420374 - ARC') as HTMLInputElement).checked,
      ).toBe(false);

      fireEvent.click(screen.getByRole('button', { name: 'Start Plan' }));
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({ demand_class: 'project', so_numbers: ['SO419517'] }),
      );
    });

    it('V3: submit sends demand_class + so_numbers for Project (final selection), demand_class only for Dealer, so_numbers with no demand_class for All (Lane D, AC-D2)', async () => {
      getCandidateOrders.mockResolvedValue([
        {
          so_number: 'SO1',
          project_label: 'P1',
          customer_name: 'C1',
          rows_total: 2,
          rows_raised_in_window: 2,
          rows_in_range: 2,
          rows_awaiting: 0,
          first_delivery: '2026-08-01',
          last_delivery: '2026-08-05',
        },
      ]);
      const { onSubmit } = await renderModal();

      // All (default): so_numbers present (Lane D keeps the Orders picker open under
      // All too), no demand_class.
      await screen.findByText('Orders');
      fireEvent.click(screen.getByRole('button', { name: 'Start Plan' }));
      expect(onSubmit.mock.calls[0][0]).not.toHaveProperty('demand_class');
      expect(onSubmit.mock.calls[0][0].so_numbers).toEqual(['SO1']);
      onSubmit.mockClear();

      // Dealer: demand_class='retail', no so_numbers - there is no Orders field to pick from.
      fireEvent.change(screen.getByTestId('demand-select'), { target: { value: 'retail' } });
      fireEvent.click(screen.getByRole('button', { name: 'Start Plan' }));
      expect(onSubmit.mock.calls[0][0].demand_class).toBe('retail');
      expect(onSubmit.mock.calls[0][0]).not.toHaveProperty('so_numbers');
      onSubmit.mockClear();

      // Project, untick the pre-selected order: empty so_numbers means "every project
      // order in range", sent as `[]`, never omitted.
      fireEvent.change(screen.getByTestId('demand-select'), { target: { value: 'project' } });
      fireEvent.click(await screen.findByLabelText('SO1 - C1'));
      fireEvent.click(screen.getByRole('button', { name: 'Start Plan' }));
      expect(onSubmit.mock.calls[0][0].demand_class).toBe('project');
      expect(onSubmit.mock.calls[0][0].so_numbers).toEqual([]);
    });

    it('V4: changing the range re-derives the pre-selection until the user edits the list, then the edit is kept', async () => {
      // Keyed on `to` rather than call order: Lane D (AC-D1) fetches candidates as soon
      // as the modal opens (Demand = All, the default) and again on every From/To
      // keystroke even before Demand switches to Project, so a `mockResolvedValueOnce`
      // pair queued by call order would land on the wrong intervening fetch.
      getCandidateOrders.mockImplementation(async (range: CandidateOrdersRange) => {
        if (range.to === '2026-08-31') {
          return [
            {
              so_number: 'SO1',
              project_label: 'P1',
              customer_name: 'C1',
              rows_total: 2,
              rows_raised_in_window: 2,
              rows_in_range: 2,
              rows_awaiting: 0,
              first_delivery: '2026-08-01',
              last_delivery: '2026-08-05',
            },
          ];
        }
        if (range.to === '2026-09-30') {
          return [
            {
              so_number: 'SO2',
              project_label: 'P2',
              customer_name: 'C2',
              rows_total: 1,
              rows_raised_in_window: 1,
              rows_in_range: 1,
              rows_awaiting: 0,
              first_delivery: '2026-09-01',
              last_delivery: '2026-09-05',
            },
          ];
        }
        return [];
      });
      const { onSubmit } = await renderModal();
      // From/To are set BEFORE Demand switches to Project (mirrors V2).
      fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-08-01' } });
      fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-08-31' } });
      fireEvent.change(screen.getByTestId('demand-select'), { target: { value: 'project' } });
      expect(await screen.findByLabelText('SO1 - C1')).toBeInTheDocument();

      // Range changes BEFORE the user has touched the list: the new pre-selection replaces
      // the old one. Only `To` moves, so this is exactly one more fetch (one new queryKey).
      fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-09-30' } });
      expect(await screen.findByLabelText('SO2 - C2')).toBeInTheDocument();
      expect((screen.getByLabelText('SO2 - C2') as HTMLInputElement).checked).toBe(true);

      // Now the user edits the list by hand.
      fireEvent.click(screen.getByLabelText('SO2 - C2'));

      // A further range change - even one whose candidates would re-select SO2 (still
      // rows_in_range > 0) - must not override the user's own edit. `rows_awaiting` is
      // bumped to 4 (was 0) so the fresh payload's own arrival is independently
      // observable in the DOM - waiting on the CALL COUNT alone (the review-kill finding,
      // B3) proves only that the fetch fired, not that its result was applied, so a build
      // that dropped `touchedOrdersRef.current` from the guard could still slip through if
      // the click happened before the state update flushed.
      getCandidateOrders.mockResolvedValueOnce([
        {
          so_number: 'SO2',
          project_label: 'P2',
          customer_name: 'C2',
          rows_total: 1,
          rows_raised_in_window: 1,
          rows_in_range: 1,
          rows_awaiting: 4,
          first_delivery: '2026-09-01',
          last_delivery: '2026-09-05',
        },
      ]);
      fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-10-31' } });

      // Wait on the EFFECT'S VISIBLE RESULT - the third payload's own awaiting count has
      // rendered, so the re-derive effect has definitely run again with fresh
      // `rows_in_range > 0` data for SO2 - before checking the guard held.
      await waitFor(() =>
        expect(screen.getByTestId('option-body-SO2').textContent).toContain('4 awaiting ack'),
      );
      // Fresh data says SO2 qualifies for pre-selection again; the user's own untick must
      // still win. Removing `touchedOrdersRef.current` from the guard (RunPlanningModal.tsx)
      // re-checks SO2 here and fails this assertion.
      expect((screen.getByLabelText('SO2 - C2') as HTMLInputElement).checked).toBe(false);

      fireEvent.click(screen.getByRole('button', { name: 'Start Plan' }));
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({ demand_class: 'project', so_numbers: [] }),
      );
    });
  });

  // ===========================================================================
  // AC-RF-1..8 (PLAN-reorder-plan-raised-filter.md, 22 Sep 2026) - "Inquiries raised"
  // From/To under the delivery range, Project-only, driving PRE-SELECTION only
  // (rows_in_range > 0 AND rows_raised_in_window > 0). The list itself is unchanged by
  // the window (AC-RF-3, backend-only - nothing to assert here).
  // ===========================================================================

  describe('Inquiries raised window (AC-RF-5..8)', () => {
    it('AC-RF-5: "Raised from"/"Raised to" render only while Demand = Project', async () => {
      await renderModal();
      expect(screen.queryByLabelText('Raised from')).not.toBeInTheDocument();
      expect(screen.queryByLabelText('Raised to')).not.toBeInTheDocument();

      fireEvent.change(screen.getByTestId('demand-select'), { target: { value: 'project' } });
      expect(await screen.findByLabelText('Raised from')).toBeInTheDocument();
      expect(screen.getByLabelText('Raised to')).toBeInTheDocument();

      fireEvent.change(screen.getByTestId('demand-select'), { target: { value: 'retail' } });
      await waitFor(() => expect(screen.queryByLabelText('Raised from')).not.toBeInTheDocument());
      expect(screen.queryByLabelText('Raised to')).not.toBeInTheDocument();

      // And absent again for the empty/"All" reading (V1 default), not just Dealer.
      fireEvent.change(screen.getByTestId('demand-select'), { target: { value: '' } });
      expect(screen.queryByLabelText('Raised from')).not.toBeInTheDocument();
    });

    it('AC-RF-6: with a raise window set, pre-selection is rows_in_range>0 AND rows_raised_in_window>0', async () => {
      getCandidateOrders.mockResolvedValue([
        {
          so_number: 'SOA', project_label: 'PA', customer_name: 'CA',
          rows_total: 2, rows_in_range: 2, rows_raised_in_window: 1, rows_awaiting: 0,
          first_delivery: '2026-09-01', last_delivery: '2026-09-05',
        },
        {
          so_number: 'SOB', project_label: 'PB', customer_name: 'CB',
          rows_total: 3, rows_in_range: 3, rows_raised_in_window: 0, rows_awaiting: 0,
          first_delivery: '2026-09-01', last_delivery: '2026-09-05',
        },
        {
          so_number: 'SOC', project_label: 'PC', customer_name: 'CC',
          rows_total: 2, rows_in_range: 0, rows_raised_in_window: 2, rows_awaiting: 0,
          first_delivery: '2026-09-01', last_delivery: '2026-09-05',
        },
      ]);
      await renderModal();
      fireEvent.change(screen.getByTestId('demand-select'), { target: { value: 'project' } });
      fireEvent.change(await screen.findByLabelText('Raised from'), { target: { value: '2026-09-17' } });
      fireEvent.change(screen.getByLabelText('Raised to'), { target: { value: '2026-09-18' } });

      // Matched with a leading-anchor regex, not an exact string: the plan's own S2
      // ("the picker option label appends 'raised N' only when a window is set") means
      // the accessible name may carry a suffix once a window is typed - the pre-selection
      // fact under test does not depend on that exact display string.
      expect(await screen.findByLabelText(/^SOA - CA/)).toBeInTheDocument();
      await waitFor(() => {
        // A: rows_in_range 2 > 0 AND rows_raised_in_window 1 > 0 -> pre-selected.
        expect((screen.getByLabelText(/^SOA - CA/) as HTMLInputElement).checked).toBe(true);
        // B: rows_in_range 3 > 0 but rows_raised_in_window 0 -> NOT pre-selected, even
        // though the old rows_in_range-only rule would have picked it.
        expect((screen.getByLabelText(/^SOB - CB/) as HTMLInputElement).checked).toBe(false);
        // C: rows_raised_in_window 2 > 0 but rows_in_range 0 -> NOT pre-selected.
        expect((screen.getByLabelText(/^SOC - CC/) as HTMLInputElement).checked).toBe(false);
      });
      // The raised count used to be rendered on the option (S2's own description
      // suffix) - dropped by the owner's Lane D fix-round-1 ruling, which retires the
      // two-line row (and its description) everywhere, Project included: the menu row
      // is now ONE line, "<SO number> - <customer>[, N awaiting ack]" only. The raise
      // window still drives pre-selection above, silently.
    });

    it('AC-RF-6: clearing the raise window widens pre-selection back to rows_in_range>0', async () => {
      // The mock branches on whether a window was actually sent, exactly like the real
      // backend contract (AC-RF-2): windowed counts while raised_from/raised_to are set,
      // rows_raised_in_window === rows_total once they are cleared.
      getCandidateOrders.mockImplementation(async (range: CandidateOrdersRange) => {
        const windowed = Boolean(range.raised_from || range.raised_to);
        return [
          {
            so_number: 'SOA', project_label: 'PA', customer_name: 'CA',
            rows_total: 2, rows_in_range: 2, rows_raised_in_window: windowed ? 1 : 2,
            rows_awaiting: 0, first_delivery: '2026-09-01', last_delivery: '2026-09-05',
          },
          {
            so_number: 'SOB', project_label: 'PB', customer_name: 'CB',
            rows_total: 3, rows_in_range: 3, rows_raised_in_window: windowed ? 0 : 3,
            rows_awaiting: 0, first_delivery: '2026-09-01', last_delivery: '2026-09-05',
          },
        ];
      });

      await renderModal();
      fireEvent.change(screen.getByTestId('demand-select'), { target: { value: 'project' } });
      fireEvent.change(await screen.findByLabelText('Raised from'), { target: { value: '2026-09-17' } });
      fireEvent.change(screen.getByLabelText('Raised to'), { target: { value: '2026-09-18' } });

      // Windowed: only A qualifies.
      await waitFor(() => {
        expect((screen.getByLabelText(/^SOA - CA/) as HTMLInputElement).checked).toBe(true);
        expect((screen.getByLabelText(/^SOB - CB/) as HTMLInputElement).checked).toBe(false);
      });

      // Clear both raise inputs - the buyer has not touched the Orders list by hand, so
      // the pre-selection re-derives on the wider (unwindowed) result (V4's own guard).
      fireEvent.change(screen.getByLabelText('Raised from'), { target: { value: '' } });
      fireEvent.change(screen.getByLabelText('Raised to'), { target: { value: '' } });

      await waitFor(() => {
        expect((screen.getByLabelText(/^SOA - CA/) as HTMLInputElement).checked).toBe(true);
        expect((screen.getByLabelText(/^SOB - CB/) as HTMLInputElement).checked).toBe(true);
      });
    });

    it('AC-RF-6: without a raise window, pre-selection stays rows_in_range>0 (today\'s behaviour, unchanged)', async () => {
      getCandidateOrders.mockResolvedValue([
        {
          so_number: 'SOA', project_label: 'PA', customer_name: 'CA',
          // No window -> rows_raised_in_window === rows_total, same as the backend
          // contract (AC-RF-2).
          rows_total: 2, rows_in_range: 2, rows_raised_in_window: 2, rows_awaiting: 0,
          first_delivery: '2026-09-01', last_delivery: '2026-09-05',
        },
        {
          so_number: 'SOB', project_label: 'PB', customer_name: 'CB',
          rows_total: 3, rows_in_range: 3, rows_raised_in_window: 3, rows_awaiting: 0,
          first_delivery: '2026-09-01', last_delivery: '2026-09-05',
        },
        {
          so_number: 'SOC', project_label: 'PC', customer_name: 'CC',
          rows_total: 2, rows_in_range: 0, rows_raised_in_window: 2, rows_awaiting: 0,
          first_delivery: '2026-09-01', last_delivery: '2026-09-05',
        },
      ]);
      await renderModal();
      fireEvent.change(screen.getByTestId('demand-select'), { target: { value: 'project' } });

      expect(await screen.findByLabelText('SOA - CA')).toBeInTheDocument();
      await waitFor(() => {
        expect((screen.getByLabelText('SOA - CA') as HTMLInputElement).checked).toBe(true);
        expect((screen.getByLabelText('SOB - CB') as HTMLInputElement).checked).toBe(true);
        expect((screen.getByLabelText('SOC - CC') as HTMLInputElement).checked).toBe(false);
      });
    });

    it('AC-RF-7: typing a raise window calls getCandidateOrders with raised_from/raised_to alongside from/to', async () => {
      getCandidateOrders.mockResolvedValue([]);
      await renderModal();
      fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-08-01' } });
      fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-10-31' } });
      fireEvent.change(screen.getByTestId('demand-select'), { target: { value: 'project' } });
      fireEvent.change(await screen.findByLabelText('Raised from'), { target: { value: '2026-09-17' } });
      fireEvent.change(screen.getByLabelText('Raised to'), { target: { value: '2026-09-18' } });

      await waitFor(() =>
        expect(getCandidateOrders).toHaveBeenLastCalledWith({
          from: '2026-08-01',
          to: '2026-10-31',
          raised_from: '2026-09-17',
          raised_to: '2026-09-18',
        }),
      );
    });
  });

  // ===========================================================================
  // Lane D (PLAN-order-sheet-oi-reports-22sep.md, AC-D1) - Demand = All keeps the Orders
  // picker (project SOs only, same "everything in range ticked" rule as Project), a
  // one-line closed trigger ("SO1, SO2 +12"), and one-line menu rows (no two-line
  // description). Today: the Orders field is hidden for every demand EXCEPT
  // `demand === 'project'` (`RunPlanningModal.tsx` "demand === 'project' ? (...)"), so
  // every test in this block that opens the picker under All (the default, unswitched
  // demand) is RED for that one reason - a genuinely missing field, not a broken fixture.
  //
  // NOTE (measured against `test('V1: ... Orders is absent for All and Dealer ...')`
  // above): that existing assertion (`expect(screen.queryByText('Orders')).not.toBeIn
  // TheDocument()` for the unswitched/All state) PINS the OLD contract this lane
  // deliberately changes - implementing AC-D1 flips that one line of V1 from absent to
  // present. Left as-is here (not the tester's edit to make); the coder updates it
  // alongside the fix.
  // ===========================================================================

  describe('Lane D - Demand = All keeps the Orders picker, so_numbers with no demand_class (AC-D1/AC-D2)', () => {
    it('AC-D1: Orders picker renders under Demand = All (the default, unswitched state)', async () => {
      getCandidateOrders.mockResolvedValueOnce([
        {
          so_number: 'SO1', project_label: 'P1', customer_name: 'C1',
          rows_total: 2, rows_in_range: 2, rows_raised_in_window: 2, rows_awaiting: 0,
          first_delivery: '2026-08-01', last_delivery: '2026-08-05',
        },
      ]);
      await renderModal();
      // Unswitched demand === '' (All) - no click on the demand select at all.
      expect(await screen.findByText('Orders')).toBeInTheDocument();
    });

    it('AC-D1: every candidate order with rows_in_range > 0 is pre-ticked under All, same rule as Project', async () => {
      getCandidateOrders.mockResolvedValueOnce([
        {
          so_number: 'SO1', project_label: 'P1', customer_name: 'C1',
          rows_total: 2, rows_in_range: 2, rows_raised_in_window: 2, rows_awaiting: 0,
          first_delivery: '2026-08-01', last_delivery: '2026-08-05',
        },
        {
          so_number: 'SO2', project_label: 'P2', customer_name: 'C2',
          rows_total: 3, rows_in_range: 0, rows_raised_in_window: 3, rows_awaiting: 0,
          first_delivery: '2026-08-01', last_delivery: '2026-08-05',
        },
      ]);
      await renderModal();
      await waitFor(() => {
        expect((screen.getByLabelText('SO1 - C1') as HTMLInputElement).checked).toBe(true);
        expect((screen.getByLabelText('SO2 - C2') as HTMLInputElement).checked).toBe(false);
      });
    });

    it('AC-D2: submitting under All sends so_numbers and NO demand_class', async () => {
      getCandidateOrders.mockResolvedValueOnce([
        {
          so_number: 'SO1', project_label: 'P1', customer_name: 'C1',
          rows_total: 2, rows_in_range: 2, rows_raised_in_window: 2, rows_awaiting: 0,
          first_delivery: '2026-08-01', last_delivery: '2026-08-05',
        },
      ]);
      const { onSubmit } = await renderModal();
      await screen.findByText('Orders');
      fireEvent.click(screen.getByRole('button', { name: 'Start Plan' }));

      expect(onSubmit.mock.calls[0][0]).not.toHaveProperty('demand_class');
      expect(onSubmit.mock.calls[0][0].so_numbers).toEqual(['SO1']);
    });

    it('AC-D6: Demand = Dealer still shows no Orders picker (unchanged)', async () => {
      await renderModal();
      fireEvent.change(screen.getByTestId('demand-select'), { target: { value: 'retail' } });
      await waitFor(() => expect(screen.queryByText('Orders')).not.toBeInTheDocument());
    });

    it('AC-D1b: the From/To range section is labelled "Project delivery range"', async () => {
      await renderModal();
      expect(screen.getByText('Project delivery range')).toBeInTheDocument();
      expect(screen.queryByText('Sales orders needed')).not.toBeInTheDocument();
    });

    it('AC-D1: the closed trigger reads ONE line, first two SO numbers then +x for the rest', async () => {
      const orders = Array.from({ length: 14 }, (_, i) => ({
        so_number: `SO${i + 1}`, project_label: `P${i + 1}`, customer_name: `C${i + 1}`,
        rows_total: 1, rows_in_range: 1, rows_raised_in_window: 1, rows_awaiting: 0,
        first_delivery: '2026-08-01', last_delivery: '2026-08-05',
      }));
      getCandidateOrders.mockResolvedValueOnce(orders);
      await renderModal();
      await screen.findByLabelText('SO1 - C1');

      const trigger = await screen.findByTestId(/trigger-label-/);
      expect(trigger.textContent).toBe('SO1, SO2 +12');
      // Fix round 3 item 2: `truncate` + `title` (every selected SO number, not just the
      // two shown) - the ADR-PRODUCT-STANDARDS pattern every other long-text cell uses,
      // so a hover/long-press at 375px still reads the full pick.
      const span = trigger.querySelector('span');
      expect(span?.className).toContain('truncate');
      expect(span?.title).toBe(
        Array.from({ length: 14 }, (_, i) => `SO${i + 1}`).join(', '),
      );
    });

    it('AC-D1: menu rows are one line each - "<SO number> - <customer>[, N awaiting ack]", no second description line', async () => {
      getCandidateOrders.mockResolvedValueOnce([
        {
          so_number: 'SO1', project_label: 'P1', customer_name: 'C1',
          rows_total: 5, rows_in_range: 5, rows_raised_in_window: 5, rows_awaiting: 3,
          first_delivery: '2026-08-01', last_delivery: '2026-08-05',
        },
      ]);
      await renderModal();
      const body = await screen.findByTestId('option-body-SO1');
      // Owner ruling (Lane D fix round 1): the awaiting-ack count DOES join this one
      // line when non-zero - only the old "N lines in range" description is gone.
      expect(body.textContent).toBe('SO1 - C1, 3 awaiting ack');
      expect(body.textContent).not.toContain('lines in range');
    });
  });
});
