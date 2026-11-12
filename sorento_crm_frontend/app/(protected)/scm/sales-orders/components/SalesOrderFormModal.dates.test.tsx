/**
 * DATE-PICKER-UNIFY slice B: SalesOrderFormModal "Requested delivery date" is a typeable
 * DatePickerField that still sends requested_delivery_date as YYYY-MM-DD.
 * Harness copied from SalesOrderFormModal.test.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
  });
}
if (!window.ResizeObserver) {
  (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

type StubOption = { value: string; label: string };

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    fetchOptions,
    selectedOption,
    placeholder,
  }: {
    value: string;
    onChange: (v: string) => void;
    options?: StubOption[];
    fetchOptions?: (query: string, pageIndex: number) => Promise<StubOption[]>;
    selectedOption?: StubOption;
    placeholder?: string;
  }) => {
    const [fetched, setFetched] = React.useState<StubOption[]>([]);
    const [query, setQuery] = React.useState('');
    React.useEffect(() => {
      if (!fetchOptions) return;
      let live = true;
      void fetchOptions(query, 0).then((rows) => {
        if (live) setFetched(rows);
      });
      return () => {
        live = false;
      };
    }, [fetchOptions, query]);

    if (!fetchOptions) {
      return (
        <select
          aria-label={placeholder}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">{placeholder}</option>
          {(options ?? []).map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      );
    }
    return (
      <div data-testid="product-field">
        <input
          aria-label={`Search ${placeholder}`}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        {/* What the trigger reads: the caller's own label for the picked code, which is the
            only thing standing between the user and a bare SKU once the search moves on. */}
        <span data-testid="product-trigger">{selectedOption?.label ?? value}</span>
        {fetched.map((o) => (
          <button type="button" key={o.value} onClick={() => onChange(o.value)}>
            {o.label}
          </button>
        ))}
      </div>
    );
  },
}));

vi.mock('../../hooks/useScmOptions', () => ({
  useOrderTypeOptions: () => ({
    data: [
      { value: 'dealer', label: 'Dealer' },
      { value: 'project', label: 'Project' },
    ],
    isLoading: false,
  }),
  useCustomerOptions: () => ({
    data: [{ value: '300-R009', label: 'Rowenda Kitchen Sdn Bhd', description: 'DEALER' }],
    isLoading: false,
  }),
}));

/** The page the server answers with when nothing is typed. The codes a person is most likely
 *  to want are deliberately NOT in it - they only come back for a query, which is what the
 *  old capped static list could never do. */
const FIRST_PAGE: StubOption[] = [
  { value: 'SRTWT7408', label: 'SRTWT7408 · Wall-hung WC 7408' },
  { value: 'CW-BASIN-450', label: 'CW-BASIN-450 · Ceramic Wash Basin 450mm' },
];
const OFF_FIRST_PAGE: StubOption[] = [
  { value: 'CB2907', label: 'CB2907 · Concealed cistern 2907' },
  { value: 'SRTWT7445-LV', label: 'SRTWT7445-LV · Wall-hung WC 7445 LV' },
];

// The page index is still recorded on every call (the assertions read it off the spy); the
// stub answers the same one page for each, since paging is `SearchableSelect`'s own concern.
const searchProductOptions = vi.fn<(query: string, pageIndex?: number) => Promise<StubOption[]>>(
  async (query) => {
    const q = query.trim().toLowerCase();
    if (!q) return FIRST_PAGE;
    return [...FIRST_PAGE, ...OFF_FIRST_PAGE].filter((o) => o.label.toLowerCase().includes(q));
  },
);

vi.mock('../../services/scmOptionsService', () => ({
  SELECT_PAGE_SIZE: 50,
  searchProductOptions: (query: string, pageIndex?: number) =>
    searchProductOptions(query, pageIndex),
}));

import { SalesOrderFormModal } from './SalesOrderFormModal';

async function renderModal(
  over: Partial<React.ComponentProps<typeof SalesOrderFormModal>> = {},
) {
  const onSubmit = vi.fn(async () => {});
  const onOpenChange = vi.fn();
  render(
    <SalesOrderFormModal
      open
      onOpenChange={onOpenChange}
      onSubmit={onSubmit}
      isPending={false}
      {...over}
    />,
  );
  // Wait out the product field's first server search, so nothing resolves after the test.
  await screen.findByText(FIRST_PAGE[0].label);
  return { onSubmit, onOpenChange };
}

/** The date field's Label carries no `htmlFor`, and the dialog renders through a portal. */
const dateInput = () =>
  document.body.querySelector('input[type="date"]') as HTMLInputElement;

/** Fill the two required header fields, so a test about the lines is about the lines. */
function fillHeader() {
  fireEvent.change(screen.getByLabelText('Select type'), { target: { value: 'project' } });
  fireEvent.change(screen.getByLabelText('Select customer'), { target: { value: '300-R009' } });
}

beforeEach(() => vi.clearAllMocks());


describe('SalesOrderFormModal - requested delivery date (DATE-PICKER-UNIFY slice B)', () => {
  it('AC1: there is no native date input, the field is a typeable dd/mm/yyyy box', async () => {
    await renderModal();
    expect(document.body.querySelector('input[type="date"]')).toBeNull();
    expect(screen.getByPlaceholderText('DD/MM/YYYY')).toBeInTheDocument();
  });

  it('AC2/AC9: typing 05/11/2026 and blurring sends requested_delivery_date 2026-11-05', async () => {
    const { onSubmit } = await renderModal();
    fillHeader();
    const date = screen.getByPlaceholderText('DD/MM/YYYY');
    fireEvent.change(date, { target: { value: '05/11/2026' } });
    fireEvent.blur(date);
    fireEvent.click(screen.getByRole('button', { name: FIRST_PAGE[0].label }));
    fireEvent.change(screen.getByRole('spinbutton'), { target: { value: '12' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create sales order' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ requested_delivery_date: '2026-11-05' }),
    );
  });
});
