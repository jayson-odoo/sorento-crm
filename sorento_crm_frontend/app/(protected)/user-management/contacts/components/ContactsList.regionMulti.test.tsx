/**
 * FILTER-MULTISELECT PR2: the contacts Filters popover's Region takes several values (OR within the
 * filter, AND across), one comma-joined param and one chip. An older link with one value reads back as
 * a one-value filter, and the URL carries the value comma-joined. Harness mirrors
 * ContactsList.multiFilters.test.tsx.
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

describe('ContactsList - multi Region filter', () => {
  it('is a multi control', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    expect((await screen.findByLabelText('Region: any')).hasAttribute('multiple')).toBe(true);
  });

  it('two regions go to the API comma-joined, with one chip naming both', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await screen.findByLabelText('Region: any'), ['west', 'east']);
    await waitFor(() => expect(lastFilters().region).toBe('west,east'));
    await user.keyboard('{Escape}');
    expect(await screen.findByText(/^Region: West.*East/)).toBeInTheDocument();
    await waitFor(() => expect(within(filtersButton()).getByText('1')).toBeInTheDocument());
  });

  it('clearing the chip drops the whole filter', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await screen.findByLabelText('Region: any'), ['west', 'east']);
    await waitFor(() => expect(lastFilters().region).toBe('west,east'));
    await user.keyboard('{Escape}');
    const before = getContactsMock.mock.calls.length;
    await user.click(await screen.findByRole('button', { name: /^Clear filter: Region: West.*East/ }));
    await waitFor(() => expect(screen.queryByText(/^Region: West.*East/)).toBeNull());
    // Clearing returns to the unfiltered query, already cached (the list keeps staleTime: Infinity),
    // so a refetch is optional; any request made after clearing must not carry the region.
    for (const call of getContactsMock.mock.calls.slice(before)) {
      expect((call[1] as Record<string, string>).region).toBeUndefined();
    }
    await user.click(filtersButton());
    const control = (await screen.findByLabelText('Region: any')) as HTMLSelectElement;
    expect(control.selectedOptions).toHaveLength(0);
  });

  it('writes the comma-joined value to the URL', async () => {
    const spy = vi.spyOn(window.history, 'replaceState');
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await screen.findByLabelText('Region: any'), ['west', 'east']);
    await waitFor(() => {
      const written = spy.mock.calls.map((c) => String(c[2])).join(' ');
      expect(decodeURIComponent(written)).toContain('region=west,east');
    });
    spy.mockRestore();
  });

  it('reads a comma-joined URL back into the filter and one chip', async () => {
    url.search = 'region=west,east';
    renderList();
    await screen.findByText('+60100000031');
    await waitFor(() => expect(lastFilters().region).toBe('west,east'));
    expect(await screen.findByText(/^Region: West.*East/)).toBeInTheDocument();
  });

  it('an older link with one region reads back as a one-value filter, named', async () => {
    url.search = 'region=east';
    renderList();
    await screen.findByText('+60100000031');
    await waitFor(() => expect(lastFilters().region).toBe('east'));
    expect(await screen.findByText(/^Region: East/)).toBeInTheDocument();
  });

  it('ANDs across Tier', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await screen.findByLabelText('Region: any'), ['west', 'east']);
    await user.selectOptions(screen.getByLabelText('Tier: any'), ['dealer']);
    await waitFor(() => expect(lastFilters()).toMatchObject({ region: 'west,east', tier: 'dealer' }));
  });
});
