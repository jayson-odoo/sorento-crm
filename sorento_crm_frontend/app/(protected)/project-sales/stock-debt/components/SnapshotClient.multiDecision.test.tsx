/**
 * FILTER-MULTISELECT PR6: the stock debt snapshot page's Decision filter takes several values (OR); one
 * comma-joined set reaches the service, pseudo-values (Decided / Undecided) combine like any other value,
 * clearing sends nothing.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;

const SNAP = 'a1b2c3d4-0000-4000-8000-000000000001';
const NEXT_SNAP = 'a1b2c3d4-0000-4000-8000-000000000002';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => `/project-sales/stock-debt/snapshots/${SNAP}`,
  useSearchParams: () => new URLSearchParams(''),
  useParams: () => ({ id: SNAP }),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: vi.fn().mockResolvedValue({ listing_key: 'x', config: null }),
  upsertUserListColumnConfig: vi.fn(),
  resetUserListColumnConfig: vi.fn(),
}));
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { id: 'u-1', name: 'Jayson Foundryx' } }, status: 'authenticated' }),
}));
vi.mock('@/components/common/PageHeader', () => ({
  PageHeader: ({ title, actions }: { title: React.ReactNode; actions?: React.ReactNode }) => (
    <header>
      <h1>{title}</h1>
      {actions}
    </header>
  ),
}));
vi.mock('@/lib/toast', () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}));
import { toast } from '@/lib/toast';

let permissions = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => permissions.has(slug),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    value?: string;
    onChange: (value: string) => void;
    options?: { value: string; label: string }[];
    clearable?: boolean;
    placeholder?: string;
    disabled?: boolean;
    'aria-label'?: string;
  }) => (
    <select
      id={props.id}
      aria-label={props['aria-label']}
      value={props.value ?? ''}
      data-clearable={props.clearable ? 'true' : 'false'}
      disabled={props.disabled}
      onChange={(event) => props.onChange(event.target.value)}
    >
      <option value="">{props.placeholder ?? ''}</option>
      {(props.options ?? []).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

vi.mock('../../_shared/hooks/useReserveRowOptions', () => ({
  useReserveRowOptions: (entries: Array<{ key: string }>) =>
    Object.fromEntries(
      entries.map((entry) => [
        entry.key,
        {
          isLoading: false,
          defaultWarehouseId: 'wh-brw',
          options: [
            { value: 'wh-brw', label: 'BRW  available 972' },
            { value: 'wh-mwh', label: 'MWH  available 0' },
          ],
          availableQtyByWarehouseId: { 'wh-brw': 972, 'wh-mwh': 0 },
        },
      ]),
    ),
}));

const parkedAction = vi.fn();
vi.mock('../../_shared/hooks/useParkedSendActions', () => ({
  useParkedSendActions: () => ({
    actions: [
      {
        key: 'send-parked-requests',
        label: 'Send all parked requests to CS (2)',
        disabled: false,
        onClick: parkedAction,
      },
      {
        key: 'send-parked-notices',
        label: 'Send all parked reserves to purchasing (0)',
        disabled: true,
        disabledReason: 'Nothing of yours is parked',
        onClick: vi.fn(),
      },
    ],
    dialog: <div data-testid="parked-dialog-node" />,
  }),
}));

const getSnapshot = vi.fn();
const listSnapshotRows = vi.fn();
const setSnapshotDecision = vi.fn();
const exportSnapshot = vi.fn();
vi.mock('../services/stockDebtSnapshotService', () => ({
  getSnapshot: (...args: unknown[]) => getSnapshot(...args),
  listSnapshotRows: (...args: unknown[]) => listSnapshotRows(...args),
  setSnapshotDecision: (...args: unknown[]) => setSnapshotDecision(...args),
  exportSnapshot: (...args: unknown[]) => exportSnapshot(...args),
  getSnapshotRowLines: vi.fn().mockResolvedValue({ lines: [] }),
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

import { SnapshotClient } from './SnapshotClient';

function header(over: Record<string, unknown> = {}) {
  return {
    id: SNAP,
    name: 'Stock Debt 15/10/2026',
    filters: {
      query: '',
      book: 'project',
      location: [],
      exclude_location: [],
      only_debt: true,
      date_from: '2023-01-01',
      date_to: '2027-05-31',
      supplier_ids: [],
      projected: false,
      show_aux: true,
    },
    filters_label:
      'Book Project · All locations · Delivery 01/01/2023 to 31/05/2027 · Only in debt · Stock and PO columns',
    months: ['2026-10', '2027-01'],
    tba_month: '2030-01',
    totals: {
      months: { '2026-10': -3692, '2027-01': -109893 },
      tba: 0,
      undated: 0,
      unlocated: 0,
      total: -507942,
      pool_on_hand: 162636,
      pool_po_qty: 0,
      pool_incoming_qty: 21121,
      dealer_outstanding: -7335,
    },
    row_count: 550,
    decided_count: 5,
    created_by_name: 'Jayson Foundryx',
    created_at: '2026-10-15T03:53:00Z',
    can_delete: true,
    prev_id: null,
    next_id: NEXT_SNAP,
    ...over,
  };
}

function snapRow(over: Record<string, unknown> = {}) {
  return {
    row_id: 'f0000000-0000-4000-8000-000000000001',
    product_id: 'f0000000-0000-4000-8000-0000000000a1',
    product_code: 'ACC6001',
    product_name: 'Acc 6001 coupling',
    months: [
      { key: '2026-10', balance: -93, tone: 'red' },
      { key: '2027-01', balance: -156, tone: 'red' },
    ],
    tba: 0,
    undated: 0,
    unlocated: 0,
    total: -369,
    supplier_id: null,
    supplier_name: null,
    category_code: null,
    pool_on_hand: 0,
    pool_po_qty: 0,
    pool_incoming_qty: 0,
    dealer_outstanding: 0,
    decision: null,
    decision_warehouse_id: null,
    decision_warehouse_code: null,
    decision_note: null,
    decided_by_name: null,
    decided_at: null,
    ...over,
  };
}

const ROWS = [
  snapRow(),
  snapRow({
    row_id: 'f0000000-0000-4000-8000-000000000002',
    product_code: 'SRTWT904-NL',
    product_name: null,
    total: -223,
    months: [
      { key: '2026-10', balance: 97, tone: 'green' },
      { key: '2027-01', balance: -30, tone: 'red' },
    ],
    decision: 'reserve',
    decision_warehouse_id: 'wh-brw',
    decision_warehouse_code: 'BRW',
    decision_note: 'Reserve all 223 from BRW',
    decided_by_name: 'Jayson Foundryx',
    decided_at: '2026-10-15T06:10:00Z',
  }),
  snapRow({
    row_id: 'f0000000-0000-4000-8000-000000000003',
    product_code: 'C-FH14',
    product_name: null,
    total: -23638,
    decision: 'buy',
  }),
  snapRow({
    row_id: 'f0000000-0000-4000-8000-000000000004',
    product_code: 'SRT23-CR',
    product_name: null,
    total: -633,
    decision: 'ignore',
    decision_note: 'Already reserved on OI-2609-0733',
  }),
];

function rowsEnvelope(rows = ROWS, total = 550) {
  return { data: rows, pagination: { total, page: 1, limit: 25 } };
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SnapshotClient snapshotId={SNAP} />
    </QueryClientProvider>,
  );
}

function rowOf(code: string): HTMLElement {
  return screen.getByText(code).closest('tr') as HTMLElement;
}

function pick(scope: HTMLElement, name: string | RegExp) {
  return within(scope).queryByRole('radio', { name }) ?? within(scope).getByRole('button', { name });
}

beforeEach(() => {
  vi.clearAllMocks();
  permissions = new Set(['projects.stock_debt.view']);
  getSnapshot.mockResolvedValue(header());
  listSnapshotRows.mockResolvedValue(rowsEnvelope());
  setSnapshotDecision.mockResolvedValue(snapRow());
  exportSnapshot.mockResolvedValue({ id: 'd-1', status: 'pending' });
});


const setOf = (v: unknown): string[] =>
  (Array.isArray(v) ? v.map(String) : String(v ?? '').split(',')).map((s) => s.trim()).filter(Boolean).sort();
const lastDecision = () => {
  const args = listSnapshotRows.mock.calls.at(-1) as unknown[];
  const opts = args.find((a, i) => i > 0 && a && typeof a === 'object') as Record<string, unknown>;
  return opts.decision;
};
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

describe('Stock debt snapshot - multi Decision filter', () => {
  it('Decision is a multi control', async () => {
    renderPage();
    await screen.findByText('ACC6001');
    expect((await box('reserve')).hasAttribute('multiple')).toBe(true);
  });

  it('two decisions reach the service as one set', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('ACC6001');
    await user.selectOptions(await box('reserve'), ['reserve', 'buy']);
    await waitFor(() => expect(setOf(lastDecision())).toEqual(['buy', 'reserve']));
  });

  it('a pseudo-value combines with a real one', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('ACC6001');
    await user.selectOptions(await box('reserve'), ['undecided', 'reserve']);
    await waitFor(() => expect(setOf(lastDecision())).toEqual(['reserve', 'undecided']));
  });

  it('clearing sends no decision, never an "all" value', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('ACC6001');
    await user.selectOptions(await box('reserve'), ['reserve', 'buy']);
    await waitFor(() => expect(setOf(lastDecision())).toEqual(['buy', 'reserve']));
    await user.deselectOptions(await box('reserve'), ['reserve', 'buy']);
    await waitFor(() => expect(setOf(lastDecision())).toEqual([]));
  });
});
