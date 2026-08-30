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

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}

type StubOption = { value: string; label: string };

// Stub the multi-select as a group of checkboxes so selection is deterministic. There
// are now TWO of them on this modal, so the group is labelled by its placeholder
// rather than a hard-coded name. Async mode (`fetchOptions`) is stubbed as well: a search
// box drives the fetch, exactly as the real component does after its debounce.
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({
    value,
    onChange,
    options,
    fetchOptions,
    selectedOptions,
    placeholder,
  }: {
    value: string[];
    onChange: (v: string[]) => void;
    options?: StubOption[];
    fetchOptions?: (query: string) => Promise<StubOption[]>;
    selectedOptions?: StubOption[];
    placeholder?: string;
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
    return (
      <div aria-label={placeholder ?? 'multi-select'}>
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
            {o.label}
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

import { RunPlanningModal } from './RunPlanningModal';

async function renderModal(over: Partial<React.ComponentProps<typeof RunPlanningModal>> = {}) {
  const onSubmit = vi.fn();
  const onOpenChange = vi.fn();
  render(
    <RunPlanningModal open onOpenChange={onOpenChange} onSubmit={onSubmit} isSubmitting={false} {...over} />,
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
    expect(screen.getByText('Sales order cut-off')).toBeInTheDocument();
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

  it('B1: fields read top to bottom Sales order cut-off, Warehouses, Products', async () => {
    await renderModal();
    // The dialog renders through a portal, so the labels are on `document.body`.
    const labels = Array.from(document.body.querySelectorAll('label, [data-slot="label"]'))
      .map((el) => el.textContent?.trim())
      .filter((t): t is string =>
        t === 'Sales order cut-off' || t === 'Warehouses' || t === 'Products',
      );
    expect(labels).toEqual(['Sales order cut-off', 'Warehouses', 'Products']);
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

  describe('Sales order cut-off (B2: a past date silently plans zero demand)', () => {
    it('sets the date input\'s own min to today, so the picker cannot offer the past', async () => {
      await renderModal();
      const input = screen.getByLabelText('Sales order cut-off') as HTMLInputElement;
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
      fireEvent.change(screen.getByLabelText('Sales order cut-off'), { target: { value: '2000-01-01' } });
      fireEvent.click(screen.getByRole('button', { name: 'Start Plan' }));

      expect(onSubmit).not.toHaveBeenCalled();
      expect(screen.getByText(/cut-off cannot be in the past/i)).toBeInTheDocument();
    });

    it('accepts today and a future date', async () => {
      const { onSubmit } = await renderModal();
      fireEvent.click(screen.getByLabelText('Kuala Lumpur DC'));
      fireEvent.change(screen.getByLabelText('Sales order cut-off'), { target: { value: '2099-12-31' } });
      fireEvent.click(screen.getByRole('button', { name: 'Start Plan' }));

      expect(onSubmit).toHaveBeenCalledWith({
        warehouse_codes: ['WH-KL'],
        product_codes: [],
        plan_horizon_date: '2099-12-31',
      });
    });
  });
});
