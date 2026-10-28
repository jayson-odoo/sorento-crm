/**
 * PORTAL-P4-REQUESTS S3 (P4-22, P4-23, P4-26): the Purchase Request and Sponsorship Form list for a LIMITED user
 * (holds `.view_own`, not `.view`) and an unchanged staff user (control), both kinds through one component.
 * Scaffolding copied from StockInquiriesList.requestScope.test.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

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
Element.prototype.scrollIntoView = vi.fn();

vi.mock('next/navigation', () => ({
  usePathname: () => '/procurement-management/purchase-requests',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: vi.fn(async (listingKey: string) => ({ listing_key: listingKey, config: null })),
  upsertUserListColumnConfig: vi.fn(async (listingKey: string, config: unknown) => ({ listing_key: listingKey, config })),
  resetUserListColumnConfig: vi.fn(async () => undefined),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() } }));
vi.mock('@/components/my-downloads/EntityDownloadsButton', () => ({
  EntityDownloadsButton: () => <span>downloads</span>,
}));
vi.mock('@/services/userSelectService', () => ({
  getUserLookup: vi.fn().mockResolvedValue([{ id: 'u-1', name: 'ZZT Alice' }]),
}));
vi.mock('@/components/common/LookupBoundLabel', () => ({
  default: ({ value }: { value: string }) => <span>{value}</span>,
}));

vi.mock('@/components/common/SearchableMultiSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableMultiSelect')>();
  type Props = Parameters<typeof actual.SearchableMultiSelect>[0];
  const Stub = ({ value, onChange, options, placeholder }: Props) => (
    <select multiple aria-label={placeholder ?? 'multi'} value={value}
      onChange={(e) => onChange(Array.from(e.target.selectedOptions, (o) => o.value))}>
      {(options ?? []).map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
  return { ...actual, SearchableMultiSelect: (props: Props) => <Stub {...props} /> };
});

let held = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => held.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => held.has(s)),
  usePermissions: () => ({ permissionSet: held, permissions: [...held], isLoading: false, isError: false }),
}));

const hooks = vi.hoisted(() => ({ usePurchaseRequests: vi.fn() }));
vi.mock('../hooks/usePurchaseRequests', () => ({
  usePurchaseRequests: (...a: unknown[]) => hooks.usePurchaseRequests(...a),
  useBulkDeletePurchaseRequests: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
}));

import PurchaseRequestsList from './PurchaseRequestsList';

type Kind = 'purchase_request' | 'sponsorship_form';
const KINDS: Array<{ kind: Kind; base: string; number: string; basePath: string; numberTitle: RegExp; variable: string }> = [
  {
    kind: 'purchase_request',
    base: 'procurement.purchase_requests',
    number: 'PR26-0001',
    basePath: '/procurement-management/purchase-requests',
    numberTitle: /number/i,
    variable: 'Purpose',
  },
  {
    kind: 'sponsorship_form',
    base: 'procurement.sponsorship_forms',
    number: 'SF26-0001',
    basePath: '/procurement-management/sponsorship-forms',
    numberTitle: /number/i,
    variable: 'Sponsor Subject',
  },
];

function renderList(k: (typeof KINDS)[number], slugs: string[]) {
  held = new Set(slugs);
  hooks.usePurchaseRequests.mockReturnValue({
    data: {
      data: [
        {
          id: 'pr-1',
          request_number: k.number,
          request_type: k.kind,
          approval_status: null,
          status: 'draft',
          customer_name: 'ZZT Customer',
          project_title: 'ZZT Project',
          purpose: 'ZZT purpose',
          sponsor_subject: 'others',
          sales_type: 'project',
          requested_by: 'ZZT',
          submitted_at: '2026-01-01T00:00:00',
          created_at: '2026-01-01T00:00:00',
          revision_no: 0,
          assigned_to_name: null,
          handled_by_name: null,
        },
      ],
      pagination: { page: 1, total: 1 },
    },
    isLoading: false,
    isFetching: false,
    isPlaceholderData: false,
    error: null,
    refetch: vi.fn(),
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PurchaseRequestsList
        requestType={k.kind}
        basePath={k.basePath}
        reportPermission={`${k.base}.report`}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe.each(KINDS)('$kind list, limited user', (k) => {
  const LIMITED = [`${k.base}.view_own`, `${k.base}.add`];
  const STAFF = [`${k.base}.view`, `${k.base}.add`, `${k.base}.delete`, `${k.base}.report`];

  it('shows Create (holds .add)', async () => {
    renderList(k, LIMITED);
    expect(await screen.findByText(k.number)).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /^Create$/ }).length).toBeGreaterThan(0);
  });

  it('hides Create when .add is not held', async () => {
    renderList(k, [`${k.base}.view_own`]);
    expect(await screen.findByText(k.number)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Create$/ })).toBeNull();
  });

  it('offers no bulk Delete after selecting a row', async () => {
    renderList(k, LIMITED);
    await screen.findByText(k.number);
    fireEvent.click(screen.getAllByRole('checkbox', { name: 'Select row' })[0]);
    expect(screen.queryByRole('button', { name: /^Delete$/ })).toBeNull();
  });

  it('offers no Export of other people rows after selecting a row', async () => {
    renderList(k, LIMITED);
    await screen.findByText(k.number);
    fireEvent.click(screen.getAllByRole('checkbox', { name: 'Select row' })[0]);
    expect(screen.queryByRole('button', { name: /Export/ })).toBeNull();
  });

  it('hides the Report button even when the report slug is held', async () => {
    renderList(k, [...LIMITED, `${k.base}.report`]);
    await screen.findByText(k.number);
    expect(screen.queryByRole('button', { name: /Report/ })).toBeNull();
    expect(screen.queryByRole('link', { name: /Report/ })).toBeNull();
  });

  it('status filter offers Draft', async () => {
    renderList(k, LIMITED);
    await screen.findByText(k.number);
    await userEvent.setup().click(screen.getByRole('button', { name: /^filters/i }));
    await waitFor(() => expect(document.querySelector('select[multiple] option[value="pending"]')).not.toBeNull());
    const statusBox = document.querySelector('select[multiple] option[value="pending"]')!.parentElement!;
    expect(statusBox.querySelector('option[value="draft"]')?.textContent).toBe('Draft');
  });

  it('staff control (P4-26): bulk Delete, Export and Report stay', async () => {
    renderList(k, STAFF);
    await screen.findByText(k.number);
    expect(screen.getAllByRole('link', { name: /Report/ }).length).toBeGreaterThan(0);
    fireEvent.click(screen.getAllByRole('checkbox', { name: 'Select row' })[0]);
    expect(await screen.findByRole('button', { name: /^Delete$/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Export/ })).toBeInTheDocument();
  });

  it.each([['limited', 'L'], ['staff', 'S']])('%s: every column header sorts (P4-23)', async (who) => {
    renderList(k, who === 'limited' ? LIMITED : STAFF);
    await screen.findByText(k.number);
    const titles: Array<string | RegExp> = [
      k.numberTitle, 'Rev', 'Submitted date', 'Created At', 'Status', 'Customer', 'Project Title',
      k.variable, 'Sales Type', 'Requested By', 'Assigned To', 'Handled By',
    ];
    const missing: string[] = [];
    for (const title of titles) {
      const th = screen
        .queryAllByText(title)
        .map((el) => el.closest('th'))
        .find(Boolean);
      const sortable = !!th?.querySelector('svg.lucide-chevrons-up-down, svg.lucide-arrow-up, svg.lucide-arrow-down');
      if (!sortable) missing.push(String(title));
    }
    expect(missing).toEqual([]);
  });
});
