/**
 * OCN-ORDER-CHANGE-NOTICE UAC G2 (red-first): the Order Change Notices list.
 * Component: ./OrderChangeNoticesList.tsx (default export, no props).
 *
 * Owner standing rules checked here: ONE toolbar row (Search, Filters, Columns, a button labelled
 * just "Create"); every column sorts ON THE SERVER (the header click reaches the service as
 * sort + dir); dropdown filters are multi-select (two values = OR); dates read dd/mm/yyyy; no
 * "Open"/"View" column, the row itself opens the record.
 *
 * The service module is mocked at its boundary (`listOrderChangeNotices`, `listChangeTypes`); the
 * hooks, the grid and the filters are the real ones. Contract the coder must meet:
 *  - list params handed to the service: { pageIndex, pageSize, sorting, searchQuery, status,
 *    changeTypeId, riskLevel }, the three filters as a comma string or an array (a set either way);
 *  - column ids = the backend sort keys: ocn_number, ocn_date, customer_name, customer_po_no,
 *    change_type_name, risk_level, project_title, sales_in_charge_name, status;
 *  - URL keys: status, change_type_id, risk_level.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = vi.fn();

const nav = vi.hoisted(() => ({ search: '', push: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: nav.push, replace: vi.fn() }),
  usePathname: () => '/procurement-management/order-change-notices',
  useSearchParams: () => new URLSearchParams(nav.search),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), custom: vi.fn() } }));

const perms = vi.hoisted(() => ({ has: (_slug: string): boolean => true }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => perms.has(slug),
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));
vi.mock('@/services/userSelectService', () => ({
  getUserLookup: vi.fn(async () => [{ id: 'zzt-u1', name: 'Sales Person A' }]),
}));

const svc = vi.hoisted(() => ({ list: vi.fn(), types: vi.fn() }));
vi.mock('../services/orderChangeNoticeService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/orderChangeNoticeService')>();
  return {
    ...actual,
    listOrderChangeNotices: (...args: unknown[]) => svc.list(...args),
    listChangeTypes: (...args: unknown[]) => svc.types(...args),
  };
});

// A native multi select stands in for the popover so the set sent to the service can be driven.
vi.mock('@/components/common/SearchableMultiSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableMultiSelect')>();
  const React = await import('react');
  type Props = Parameters<typeof actual.SearchableMultiSelect>[0];
  const Stub = ({ value, onChange, options, fetchOptions, placeholder }: Props) => {
    const [loaded, setLoaded] = React.useState(options ?? []);
    React.useEffect(() => {
      if (fetchOptions) void fetchOptions('', 0).then(setLoaded);
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

import OrderChangeNoticesList from './OrderChangeNoticesList';
import { CHANGE_TYPES, OCN_ID, ocnRow } from './ocnTestData';

const ROWS = [
  ocnRow(),
  ocnRow({
    id: 'a1111111-0000-4000-8000-000000000002',
    ocn_number: 'OCN26-0303',
    ocn_date: '2026-11-06',
    customer_name: 'Customer B Sdn Bhd',
    customer_po_no: '300/4800002913',
    change_type_name: 'Cancellation',
    risk_level: 'Highest',
    project_title: 'Project Beta Residence',
    status: 'submitted',
    approval_status: 'pending',
  }),
  ocnRow({
    id: 'a1111111-0000-4000-8000-000000000003',
    ocn_number: 'OCN26-0301',
    ocn_date: '2026-10-29',
    change_type_name: 'Delay',
    risk_level: 'Low',
    status: 'processed_by_cs',
    approval_status: 'approved',
  }),
];

const setOf = (v: unknown): string[] =>
  (Array.isArray(v) ? v.map(String) : String(v ?? '').split(',')).map((s) => s.trim()).filter(Boolean).sort();
const lastParams = () => svc.list.mock.calls.at(-1)?.[0] as Record<string, unknown>;
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
const openFilters = () =>
  fireEvent.pointerDown(screen.getByRole('button', { name: /filters/i }), { button: 0, ctrlKey: false });
const header = (name: string) => screen.getByRole('columnheader', { name: new RegExp(`^${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`) });

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={client}>
      <OrderChangeNoticesList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  nav.search = '';
  perms.has = () => true;
  svc.list.mockResolvedValue({ data: ROWS, pagination: { total: ROWS.length, page: 1, limit: 25 } });
  svc.types.mockResolvedValue(CHANGE_TYPES);
});
afterEach(() => cleanup());

describe('G2 columns', () => {
  const TITLES = [
    'OCN no.', 'Date', 'Customer', 'Customer PO no.', 'Type', 'Risk', 'Project', 'Sales in charge', 'Status',
  ];

  it('shows the nine columns, in the card order', async () => {
    mount();
    await screen.findByText('OCN26-0302');
    const nodes = TITLES.map(header);
    for (let i = 0; i < nodes.length - 1; i += 1) {
      expect(
        nodes[i].compareDocumentPosition(nodes[i + 1]) & Node.DOCUMENT_POSITION_FOLLOWING,
        `${TITLES[i]} should come before ${TITLES[i + 1]}`,
      ).toBeTruthy();
    }
  });

  it('has no Open / View / Actions column and no per-row buttons', async () => {
    mount();
    await screen.findByText('OCN26-0302');
    for (const name of ['Open', 'View', 'Actions', 'Action']) {
      expect(screen.queryByRole('columnheader', { name: new RegExp(`^${name}$`, 'i') })).toBeNull();
      expect(screen.queryByRole('button', { name: new RegExp(`^${name}$`, 'i') })).toBeNull();
    }
  });

  it('reads every date as dd/mm/yyyy', async () => {
    mount();
    await screen.findByText('OCN26-0302');
    expect(screen.getByText('03/11/2026')).toBeTruthy();
    expect(screen.getByText('06/11/2026')).toBeTruthy();
    expect(screen.getByText('29/10/2026')).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/2026-1[01]-\d\d/);
  });

  it('shows each value in its own cell: type, risk, project, sales in charge, customer PO', async () => {
    mount();
    await screen.findByText('OCN26-0302');
    expect(screen.getByText('Exchange')).toBeTruthy();
    expect(screen.getByText('High')).toBeTruthy();
    expect(screen.getByText('Highest')).toBeTruthy();
    expect(screen.getAllByText('Project Alpha Tower').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Sales Person A').length).toBe(3);
    expect(screen.getAllByText('XT04/3871 (R1)').length).toBeGreaterThan(0);
  });

  it('cuts long text to one line and keeps the full value on hover', async () => {
    mount();
    await screen.findByText('OCN26-0302');
    expect(screen.getAllByTitle('Customer B Sdn Bhd').length).toBeGreaterThan(0);
    expect(screen.getAllByTitle('Project Beta Residence').length).toBeGreaterThan(0);
  });

  it('draws the status as a pill with the plain word: Submitted, Pending approval, Done', async () => {
    mount();
    await screen.findByText('OCN26-0302');
    expect(screen.getByText('Submitted')).toBeTruthy();
    expect(screen.getByText('Pending approval')).toBeTruthy();
    expect(screen.getByText('Done')).toBeTruthy();
    expect(screen.queryByText('processed_by_cs')).toBeNull();
  });

  it('opens the record from the row (a link to the detail page), not from a button', async () => {
    mount();
    await screen.findByText('OCN26-0302');
    const link = document.querySelector(`a[href^="/procurement-management/order-change-notices/${OCN_ID}"]`);
    expect(link).not.toBeNull();
  });
});

describe('G2 sorting runs on the server', () => {
  it('a header click sends sort + dir to the service: asc, then desc', async () => {
    mount();
    await screen.findByText('OCN26-0302');
    fireEvent.click(within(header('Date')).getByRole('button', { name: 'Date' }));
    await waitFor(() => expect(lastParams().sorting).toEqual([{ id: 'ocn_date', desc: false }]));
    fireEvent.click(within(header('Date')).getByRole('button', { name: 'Date' }));
    await waitFor(() => expect(lastParams().sorting).toEqual([{ id: 'ocn_date', desc: true }]));
  });

  it.each([
    ['OCN no.', 'ocn_number'],
    ['Customer', 'customer_name'],
    ['Customer PO no.', 'customer_po_no'],
    ['Type', 'change_type_name'],
    ['Risk', 'risk_level'],
    ['Project', 'project_title'],
    ['Sales in charge', 'sales_in_charge_name'],
    ['Status', 'status'],
  ])('the %s header sorts by %s', async (title, key) => {
    mount();
    await screen.findByText('OCN26-0302');
    fireEvent.click(within(header(title)).getByRole('button', { name: title }));
    await waitFor(() => expect(lastParams().sorting).toEqual([{ id: key, desc: false }]));
  });
});

describe('G2 multi-select filters', () => {
  it('Status, Type and Risk are multi controls', async () => {
    mount();
    await screen.findByText('OCN26-0302');
    openFilters();
    expect((await box('draft')).hasAttribute('multiple')).toBe(true);
    expect((await box(CHANGE_TYPES[0].id)).hasAttribute('multiple')).toBe(true);
    expect((await box('Highest')).hasAttribute('multiple')).toBe(true);
  });

  it('the Status filter offers every lifecycle value with the plain word for the last two', async () => {
    mount();
    await screen.findByText('OCN26-0302');
    openFilters();
    const status = await box('draft');
    const offered = Array.from(status.options, (o) => o.value);
    for (const v of ['draft', 'submitted', 'approved', 'rejected', 'processed_by_cs', 'voided']) {
      expect(offered).toContain(v);
    }
    expect(status.querySelector('option[value="processed_by_cs"]')?.textContent).toBe('Done');
  });

  it('two statuses reach the service as one set', async () => {
    const user = userEvent.setup();
    mount();
    await screen.findByText('OCN26-0302');
    openFilters();
    await user.selectOptions(await box('draft'), ['draft', 'approved']);
    await waitFor(() => expect(setOf(lastParams().status)).toEqual(['approved', 'draft']));
  });

  it('two change types reach the service as one set', async () => {
    const user = userEvent.setup();
    mount();
    await screen.findByText('OCN26-0302');
    openFilters();
    await user.selectOptions(await box(CHANGE_TYPES[0].id), [CHANGE_TYPES[0].id, CHANGE_TYPES[2].id]);
    await waitFor(() =>
      expect(setOf(lastParams().changeTypeId)).toEqual([CHANGE_TYPES[0].id, CHANGE_TYPES[2].id].sort()),
    );
  });

  it('two risk levels reach the service as one set', async () => {
    const user = userEvent.setup();
    mount();
    await screen.findByText('OCN26-0302');
    openFilters();
    await user.selectOptions(await box('Highest'), ['High', 'Highest']);
    await waitFor(() => expect(setOf(lastParams().riskLevel)).toEqual(['High', 'Highest']));
  });

  it('two different filters combine, and clearing one sends nothing for it (no "__all__")', async () => {
    const user = userEvent.setup();
    mount();
    await screen.findByText('OCN26-0302');
    openFilters();
    await user.selectOptions(await box('draft'), ['draft']);
    await user.selectOptions(await box('Highest'), ['Highest']);
    await waitFor(() => {
      expect(setOf(lastParams().status)).toEqual(['draft']);
      expect(setOf(lastParams().riskLevel)).toEqual(['Highest']);
    });
    await user.deselectOptions(await box('draft'), ['draft']);
    await waitFor(() => expect(setOf(lastParams().status)).toEqual([]));
    expect(setOf(lastParams().riskLevel)).toEqual(['Highest']);
    for (const [params] of svc.list.mock.calls) {
      for (const key of ['status', 'changeTypeId', 'riskLevel']) {
        expect(setOf((params as Record<string, unknown>)[key])).not.toContain('__all__');
      }
    }
  });

  it('filters in the address bar are read back: one value, or a joined set', async () => {
    nav.search = `status=draft&risk_level=High,Highest&change_type_id=${CHANGE_TYPES[3].id}`;
    mount();
    await waitFor(() => expect(setOf(lastParams().status)).toEqual(['draft']));
    expect(setOf(lastParams().riskLevel)).toEqual(['High', 'Highest']);
    expect(setOf(lastParams().changeTypeId)).toEqual([CHANGE_TYPES[3].id]);
  });
});

describe('G2 the one toolbar row', () => {
  it('has Search, Filters, Columns and a button labelled exactly "Create"', async () => {
    mount();
    await screen.findByText('OCN26-0302');
    expect(screen.getByPlaceholderText(/search/i)).toBeTruthy();
    expect(screen.getByRole('button', { name: /filters/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /columns/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /^create$/i })).toBeTruthy();
    expect(screen.queryByRole('button', { name: /^(new|add|create (a |an )?\w.*)$/i })).toBeNull();
  });

  it('Create opens the new-notice page', async () => {
    mount();
    await screen.findByText('OCN26-0302');
    fireEvent.click(screen.getByRole('button', { name: /^create$/i }));
    expect(nav.push).toHaveBeenCalledWith('/procurement-management/order-change-notices/new');
  });

  it('hides Create from someone without the create permission', async () => {
    perms.has = (slug) => slug !== 'procurement.order_change_notices.create';
    mount();
    await screen.findByText('OCN26-0302');
    expect(screen.queryByRole('button', { name: /^create$/i })).toBeNull();
  });
});

describe('G2 empty and error states', () => {
  it('ends in an empty state when there are no notices', async () => {
    svc.list.mockResolvedValue({ data: [], pagination: { total: 0, page: 1, limit: 25 } });
    mount();
    await waitFor(() => expect(screen.getByText(/no (order change notices|results|data)/i)).toBeTruthy());
  });

  it('ends in an error with Try again when the list cannot load', async () => {
    svc.list.mockRejectedValue(new Error('Could not load the notices'));
    mount();
    expect(await screen.findByRole('button', { name: /try again|retry/i })).toBeTruthy();
  });
});

describe('round 4: one status word, and Pending approval as a filter value (review m8)', () => {
  it('offers Pending approval and calls a resubmitted notice Appealed, and sends the value as is', async () => {
    const user = userEvent.setup();
    mount();
    await screen.findByText('OCN26-0302');
    openFilters();
    const status = await box('pending_approval');
    expect(status.querySelector('option[value="pending_approval"]')?.textContent).toBe('Pending approval');
    expect(status.querySelector('option[value="resubmitted"]')?.textContent).toBe('Appealed');
    await user.selectOptions(status, ['pending_approval']);
    await waitFor(() => expect(setOf(lastParams().status)).toEqual(['pending_approval']));
  });
});
