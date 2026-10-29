/**
 * FILTER-MULTISELECT PR 2 slice A: the contacts Filters popover's Access type, Tier and Customer take
 * several values (OR within a filter, AND across), one comma-joined param each and one chip each.
 * An older link with one value reads back as a one-value filter. Harness mirrors
 * ContactsList.companies.test.tsx.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

if (!window.matchMedia) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false, media: query, onchange: null, addListener: vi.fn(), removeListener: vi.fn(),
    addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}
if (!('ResizeObserver' in window)) {
  (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? vi.fn();

const apiFetchMock = vi.fn();
const url = vi.hoisted(() => ({ search: '' }));
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetchMock(...a) }));
vi.mock('@/hooks/useRespondContactOutbound', () => ({
  RESPOND_CONTACTS_OUTBOUND_KEY: 'respond-contacts-outbound',
  useRespondContactOutboundMutations: () => ({
    setOne: { mutate: vi.fn(), isPending: false },
    setBulk: { mutate: vi.fn(), isPending: false },
  }),
}));
vi.mock('@/components/contacts/PortalLinkButton', () => ({ default: () => null }));
vi.mock('@/services/contactImpersonationService', () => ({ startContactImpersonation: vi.fn() }));
vi.mock('next-auth/react', () => ({ useSession: () => ({ data: { user: { email: 'admin@zzt.test' } } }) }));
vi.mock('@/lib/is-superadmin', () => ({ isSuperadminUser: () => false }));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => '/user-management/contacts',
  useSearchParams: () => new URLSearchParams(url.search),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

// Native <select> stand-in, labelled by its placeholder, so each filter is driven deterministically.
vi.mock('@/components/common/SearchableSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableSelect')>();
  type Props = Parameters<typeof actual.SearchableSelect>[0];
  const Stub = ({ value, onChange, options, placeholder, disabled }: Props) => (
    <select aria-label={placeholder ?? 'select'} value={value ?? ''} disabled={disabled}
      onChange={(e) => onChange(e.target.value)}>
      <option value="" />
      {(options ?? []).map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
  return { ...actual, SearchableSelect: (props: Props) => <Stub {...props} /> };
});

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

vi.mock('../../contact-access-types/hooks/useContactAccessTypes', () => ({
  useContactAccessTypes: () => ({
    data: [
      { code: 'zzt-a', name: 'ZZT Alpha' },
      { code: 'zzt-b', name: 'ZZT Beta' },
    ],
  }),
}));
const CUSTOMERS = [
  { value: 'cust-1', label: 'ZZT One', description: '' },
  { value: 'cust-2', label: 'ZZT Two', description: '' },
];
vi.mock('@/app/(protected)/order-management/customers/services/customerService', () => ({
  searchCustomersSelect: vi.fn(async (_q: string, _p: number, opts?: { customerId?: string }) =>
    opts?.customerId ? CUSTOMERS.filter((c) => c.value === opts.customerId) : CUSTOMERS,
  ),
}));

const BASE = {
  first_name: 'ZZT', respond_io_id: '1', outbound_enabled: true, access_type_codes: [], access_types: [],
  created_at: '2026-01-05T02:00:00', updated_at: '2026-01-05T02:00:00', linked_user_id: null, linked_user_name: null,
};
const ROW = { ...BASE, id: 'contact-1', name: 'ZZT One', last_name: 'One', phone_number: '+60100000031',
  customer_codes: [], customer_companies: [] };

const getContactsMock = vi.fn();
vi.mock('../[id]/services/contactService', () => ({
  getContacts: (...a: unknown[]) => getContactsMock(...a),
  getContact: vi.fn(),
  getContactCompanies: vi.fn(),
}));

import ContactsList from './ContactsList';

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ContactsList />
    </QueryClientProvider>,
  );
}
const lastFilters = () => {
  const calls = getContactsMock.mock.calls;
  return calls[calls.length - 1][1] as Record<string, string>;
};
const filtersButton = () => screen.getByRole('button', { name: /^filters/i });

beforeEach(() => {
  vi.clearAllMocks();
  url.search = '';
  getContactsMock.mockResolvedValue({ data: [ROW], pagination: { total: 1 } } as never);
  apiFetchMock.mockImplementation(async () => ({ ok: true, json: async () => [] }) as unknown as Response);
});
afterEach(() => cleanup());

async function openFilters(user: ReturnType<typeof userEvent.setup>) {
  renderList();
  await screen.findByText('+60100000031');
  await user.click(filtersButton());
}

describe('ContactsList - multi Access type, Tier and Customer filters', () => {
  it('are multi controls', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    for (const label of ['Access type: any', 'Tier: any', 'Customer: any']) {
      expect((await screen.findByLabelText(label)).hasAttribute('multiple')).toBe(true);
    }
  });

  it('two access types go to the API comma-joined, with one chip naming them', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await screen.findByLabelText('Access type: any'), ['zzt-a', 'zzt-b']);
    await waitFor(() => expect(lastFilters().access_type).toBe('zzt-a,zzt-b'));
    await user.keyboard('{Escape}');
    expect(await screen.findByText('Access type: ZZT Alpha, ZZT Beta')).toBeInTheDocument();
    await waitFor(() => expect(within(filtersButton()).getByText('1')).toBeInTheDocument());
  });

  it('two tiers go to the API comma-joined and clearing the chip drops the filter', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await screen.findByLabelText('Tier: any'), ['dealer', 'none']);
    await waitFor(() => expect(lastFilters().tier).toBe('dealer,none'));
    await user.keyboard('{Escape}');
    await user.click(await screen.findByRole('button', { name: 'Clear filter: Tier: Dealer, No tier' }));
    await waitFor(() => expect(screen.queryByText('Tier: Dealer, No tier')).toBeNull());
  });

  it('two customers go to the API comma-joined and the chip names both, never an id', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const select = await screen.findByLabelText('Customer: any');
    await waitFor(() => expect((select as HTMLSelectElement).options.length).toBe(2));
    await user.selectOptions(select, ['cust-1', 'cust-2']);
    await waitFor(() => expect(lastFilters().customer_id).toBe('cust-1,cust-2'));
    await user.keyboard('{Escape}');
    expect(await screen.findByText('Customer: ZZT One, ZZT Two')).toBeInTheDocument();
  });

  it('filters AND across each other', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await screen.findByLabelText('Tier: any'), ['dealer', 'office']);
    await user.selectOptions(screen.getByLabelText('Access type: any'), ['zzt-b']);
    await waitFor(() => expect(lastFilters()).toMatchObject({ tier: 'dealer,office', access_type: 'zzt-b' }));
  });

  it('an older link with one value of each reads back as one-value filters, named', async () => {
    url.search = 'tier=office&access_type=zzt-a&customer_id=cust-2';
    renderList();
    await screen.findByText('+60100000031');
    await waitFor(() =>
      expect(lastFilters()).toMatchObject({ tier: 'office', access_type: 'zzt-a', customer_id: 'cust-2' }),
    );
    expect(screen.getByText('Tier: Office')).toBeInTheDocument();
    expect(screen.getByText('Access type: ZZT Alpha')).toBeInTheDocument();
    expect(await screen.findByText('Customer: ZZT Two')).toBeInTheDocument();
  });
});
