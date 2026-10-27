/**
 * FILTER-MULTISELECT PR6: the Allocation panel's State filter takes several values (OR, client-side): two states
 * keep the lines of either, unpicking everything restores every line.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  AllocationCandidateList,
  AllocationLineRow,
  AllocationSourceRow,
} from '../../../../_shared/types/projectAllocation.types';

Element.prototype.scrollIntoView = vi.fn();
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/p1/sales-orders/so-1',
  useSearchParams: () => new URLSearchParams(''),
}));

// Without this the shared DataGrid sits in its column-preferences fetch forever and renders
// skeleton rows instead of data.
const listingKeys: (string | null | undefined)[] = [];
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: ({ listingKey }: { listingKey?: string | null }) => {
    listingKeys.push(listingKey);
    return { resetToDefaults: vi.fn(), isLoading: false };
  },
}));

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), custom: vi.fn() },
}));

const listSalesOrderAllocations = vi.fn();
const listAllocationCandidates = vi.fn();

vi.mock('../../../../_shared/services/projectAllocationService', () => ({
  listSalesOrderAllocations: (...args: unknown[]) => listSalesOrderAllocations(...args),
  listAllocationCandidates: (...args: unknown[]) => listAllocationCandidates(...args),
  listAllocationClaims: vi.fn(),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
  }: {
    value: string;
    onChange: (next: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <select
      aria-label={placeholder ?? 'select'}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="">{placeholder ?? ''}</option>
      {(options ?? []).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

vi.mock('@/components/common/SearchableMultiSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableMultiSelect')>();
  const React = await import('react');
  type Props = Parameters<typeof actual.SearchableMultiSelect>[0];
  const Stub = ({ value, onChange, options, fetchOptions, placeholder }: Props) => {
    const [loaded, setLoaded] = React.useState(options ?? []);
    React.useEffect(() => {
      if (fetchOptions) void fetchOptions('').then(setLoaded);
    }, [fetchOptions]);
    return (
      <select multiple aria-label={placeholder ?? 'multi'} value={value}
        onChange={(e) => onChange(Array.from(e.target.selectedOptions, (o) => o.value))}>
        {(fetchOptions ? loaded : (options ?? [])).map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    );
  };
  return { ...actual, SearchableMultiSelect: (props: Props) => <Stub {...props} /> };
});

import { AllocationPanel } from './AllocationPanel';

function source(overrides: Partial<AllocationSourceRow> = {}): AllocationSourceRow {
  return {
    id: 'src-1',
    source_type: 'brw',
    warehouse_id: 'wh-brw',
    warehouse_code: 'BRW',
    warehouse_name: 'Master location',
    qty: '10',
    confirmed: true,
    ...overrides,
  };
}

function line(overrides: Partial<AllocationLineRow> = {}): AllocationLineRow {
  return {
    line_id: 'l1',
    line_no: 1,
    product_id: 'prod-1',
    product_code: 'SRT382-6',
    description: 'SORENTO STAINLESS STEEL FLOOR GRATING 6" x 6"',
    qty: '10',
    uom: 'UNIT',
    delivery_date: '2026-07-01',
    state: 'unallocated',
    stock_location: null,
    allocated_qty: '0',
    outstanding_qty: '10',
    sources: [],
    ...overrides,
  };
}

const SOURCED = line({
  line_id: 'l2',
  line_no: 2,
  product_code: 'CB6633',
  description: 'CABANA S/STEEL FLOOR GRATING 6"',
  state: 'confirmed',
  stock_location: 'BRW',
  allocated_qty: '10',
  outstanding_qty: '0',
  sources: [source()],
});

const WAITING = line({
  line_id: 'l3',
  line_no: 3,
  product_code: 'SRTFV1001',
  description: 'SENSOR URINAL FLUSH VALVE',
  qty: '5',
  state: 'pending_claim',
  stock_location: null,
  allocated_qty: '0',
  outstanding_qty: '5',
  sources: [
    source({
      id: 'src-3',
      source_type: 'other_project',
      warehouse_id: 'wh-kl',
      warehouse_code: 'WH-KL',
      source_project_id: 'p2',
      source_project_code: 'PRJ-000042',
      source_project_cs_name: 'Aisyah',
      qty: '5',
      confirmed: false,
      claim_id: 'c1',
      claim_state: 'requested',
    }),
  ],
});

const CANDIDATES: AllocationCandidateList = {
  line_id: 'l1',
  line_no: 1,
  product_code: 'SRT382-6',
  description: 'SORENTO STAINLESS STEEL FLOOR GRATING 6" x 6"',
  qty: '10',
  uom: 'UNIT',
  delivery_date: '2026-07-01',
  project_code: 'PRJ-000001',
  brw_warehouse_code: 'BRW',
  candidates: [],
  plan: [],
  shortfall: '0',
  covered: false,
};

function envelope(rows: AllocationLineRow[]) {
  return { data: rows, total: rows.length, page: 1, limit: 100 };
}

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <AllocationPanel psoId="so-1" />
    </QueryClientProvider>,
  );
}

/** Radix opens its menus on pointerdown, which fireEvent.click does not send. */
function openFilters() {
  fireEvent.pointerDown(screen.getByRole('button', { name: /filters/i }), {
    button: 0,
    ctrlKey: false,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  listingKeys.length = 0;
  listSalesOrderAllocations.mockResolvedValue(envelope([]));
  listAllocationCandidates.mockResolvedValue(CANDIDATES);
});


const boxesWith = (value: string) =>
  screen.queryAllByRole('listbox').filter(
    (el) => el.hasAttribute('multiple') && el.querySelector(`option[value="${value}"]`),
  ) as HTMLSelectElement[];
async function box(value: string) {
  await waitFor(() => {
    if (!boxesWith(value).length) throw new Error(`no multi control offering option "${value}"`);
  });
  return boxesWith(value)[0];
}
const shown = (code: string) => screen.queryByText(code) !== null;

describe('AllocationPanel - multi State filter', () => {
  beforeEach(() => {
    listSalesOrderAllocations.mockResolvedValue(envelope([line(), SOURCED, WAITING]));
  });

  it('State is a multi control', async () => {
    renderPanel();
    await screen.findByText('SRT382-6');
    openFilters();
    expect((await box('confirmed')).hasAttribute('multiple')).toBe(true);
  });

  it('two states keep the lines of either', async () => {
    const user = userEvent.setup();
    renderPanel();
    await screen.findByText('SRT382-6');
    openFilters();
    await user.selectOptions(await box('confirmed'), ['unallocated', 'confirmed']);
    await waitFor(() => expect(shown('SRTFV1001')).toBe(false));
    expect(shown('SRT382-6')).toBe(true);
    expect(shown('CB6633')).toBe(true);
  });

  it('unpicking everything restores every line, with no "all" value involved', async () => {
    const user = userEvent.setup();
    renderPanel();
    await screen.findByText('SRT382-6');
    openFilters();
    await user.selectOptions(await box('confirmed'), ['unallocated', 'confirmed']);
    await waitFor(() => expect(shown('SRTFV1001')).toBe(false));
    openFilters();
    await user.deselectOptions(await box('confirmed'), ['unallocated', 'confirmed']);
    await waitFor(() => expect(shown('SRTFV1001')).toBe(true));
    expect(boxesWith('all')).toHaveLength(0);
  });
});
