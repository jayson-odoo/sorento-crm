/**
 * FILTER-MULTISELECT PR 1 (owner 27 Oct: "here need to be able to filter by companies", "show the
 * companies column also"). The Filters popover carries a multi-select Company filter (the companies
 * of the contact's linked customers, any-of) and the grid a Companies column.
 * Harness mirrors ContactsList.filtersPopover.test.tsx.
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
  useSearchParams: () => ({ get: () => null }),
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

const SORENTO = '00000000-0000-0000-0000-000000000001';
const MOCHA = '00000000-0000-0000-0000-000000000002';
const MY_CONTEXT = {
  companies: [
    { id: MOCHA, name: 'Mocha', code: 'MCH', is_active: true },
    { id: SORENTO, name: 'Sorento', code: 'SRT', is_active: true },
  ],
  active_company_id: SORENTO,
  last_active_company_id: SORENTO,
};

const BASE = {
  first_name: 'ZZT', respond_io_id: '1', outbound_enabled: true, access_type_codes: [], access_types: [],
  created_at: '2026-01-05T02:00:00', updated_at: '2026-01-05T02:00:00', linked_user_id: null, linked_user_name: null,
};
const BOTH = { ...BASE, id: 'contact-both', name: 'ZZT Both', last_name: 'Both', phone_number: '+60100000021',
  customer_codes: ['300-1 (MCH)', '300-2'], customer_companies: ['Mocha', 'Sorento'] };
const NONE = { ...BASE, id: 'contact-none', name: 'ZZT None', last_name: 'None', phone_number: '+60100000022',
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
  window.history.replaceState(null, '', '/user-management/contacts');
  getContactsMock.mockResolvedValue({ data: [BOTH, NONE], pagination: { total: 2 } } as never);
  apiFetchMock.mockImplementation(async (url: string) => ({
    ok: true,
    json: async () => (String(url).includes('/my-context') ? MY_CONTEXT : []),
  }) as unknown as Response);
});
afterEach(() => cleanup());

describe('ContactsList - Companies column', () => {
  it('has a Companies column listing the companies of the linked customers', async () => {
    renderList();
    const row = (await screen.findByText('+60100000021')).closest('tr') as HTMLElement;
    expect(screen.getByRole('button', { name: /^Companies$/ })).toBeInTheDocument();
    expect(within(row).getByText('Mocha, Sorento')).toBeInTheDocument();
  });

  it('shows a dash for a contact with no customer', async () => {
    renderList();
    const row = (await screen.findByText('+60100000022')).closest('tr') as HTMLElement;
    expect(row.textContent).not.toContain('Mocha');
    expect(within(row).getAllByText(/^\s*-\s*$/).length).toBeGreaterThan(0);
  });
});

describe('ContactsList - Company filter', () => {
  it('offers every company the viewer can switch into, by name', async () => {
    const user = userEvent.setup();
    renderList();
    await screen.findByText('+60100000021');
    await user.click(filtersButton());
    const select = await screen.findByLabelText('Company: any');
    await waitFor(() =>
      expect(Array.from((select as HTMLSelectElement).options, (o) => o.text)).toEqual(['Mocha', 'Sorento']),
    );
  });

  it('several companies go to the API as one any-of filter, with one chip naming them', async () => {
    const user = userEvent.setup();
    renderList();
    await screen.findByText('+60100000021');
    await user.click(filtersButton());
    const select = await screen.findByLabelText('Company: any');
    await waitFor(() => expect((select as HTMLSelectElement).options.length).toBe(2));
    await user.selectOptions(select, [MOCHA, SORENTO]);
    await waitFor(() => expect(lastFilters().company).toBe(`${MOCHA},${SORENTO}`));
    await user.keyboard('{Escape}');

    await waitFor(() => expect(within(filtersButton()).getByText('1')).toBeInTheDocument());
    expect(screen.getByText('Company: Mocha, Sorento')).toBeInTheDocument();
    expect(window.location.search).toContain(`company=${encodeURIComponent(`${MOCHA},${SORENTO}`)}`);
    await user.click(screen.getByRole('button', { name: 'Clear filter: Company: Mocha, Sorento' }));
    await waitFor(() => expect(screen.queryByText('Company: Mocha, Sorento')).toBeNull());
    expect(window.location.search).not.toContain('company');
  });
});
