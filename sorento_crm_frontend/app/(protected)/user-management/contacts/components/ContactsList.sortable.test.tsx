/**
 * ACCESS-SHEET-FIXES fix 5 (owner 27 Oct: "all the columns here must be sortable, all our system
 * columns should be sortable"). Every Internal Users column header is a sort button, and a click
 * asks the server for that column (`getContacts` sorting -> `buildDataGridParams` sort=<id>).
 * Same harness as `ContactsList.brandsColumn.test.tsx`.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

if (!window.matchMedia) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
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

const BASE_ROW = {
  phone_number: '+60120000701',
  respond_io_id: '10025901',
  outbound_enabled: true,
  access_type_codes: ['end_user'],
  access_types: [{ code: 'end_user', name: 'End User' }],
  created_at: '2026-01-05T02:00:00',
  updated_at: '2026-01-05T02:00:00',
  linked_user_id: null,
  linked_user_name: null,
};
const SCOPED = {
  ...BASE_ROW,
  id: 'contact-scoped',
  name: 'Scoped Sam',
  first_name: 'Scoped',
  last_name: 'Sam',
  brands: [
    { id: '11111111-1111-4111-8111-111111111111', brand_name: 'Mocha' },
    { id: '22222222-2222-4222-8222-222222222222', brand_name: 'Cabana' },
  ],
};
const OPEN = {
  ...BASE_ROW,
  id: 'contact-open',
  phone_number: '+60120000702',
  name: 'Open Olive',
  first_name: 'Open',
  last_name: 'Olive',
  brands: [],
};

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

beforeEach(() => {
  vi.clearAllMocks();
  getContactsMock.mockResolvedValue({ data: [SCOPED, OPEN], pagination: { total: 2 } } as never);
  apiFetchMock.mockResolvedValue({ ok: true, json: async () => [] } as unknown as Response);
});
afterEach(() => cleanup());

const COLUMNS: [string, string][] = [
  ['Customers', 'customers'],
  ['Companies', 'companies'],
  ['Access types', 'access_types'],
  ['Tags', 'tags'],
  ['Tag settings', 'tag_settings'],
  ['Brands', 'brands'],
  ['Tier', 'chatbot_tier'],
  ['Cost', 'cost_visible'],
  ['AI replies', 'chatbot_allowed'],
  ['Escalation', 'escalation_allowed'],
  ['Packing list', 'packing_list_allowed'],
  ['Regions', 'regions'],
  ['Stock checks', 'chatbot_stock_allowed'],
  ['User', 'linked_user'],
  ['Outbound', 'outbound_enabled'],
];

describe('ContactsList - every column sorts on the server', () => {
  it.each(COLUMNS)('the %s header sorts by %s', async (title, id) => {
    renderList();
    await screen.findByText('+60120000701');
    fireEvent.click(screen.getByRole('button', { name: new RegExp(`^${title}$`) }));
    await waitFor(() => {
      const last = getContactsMock.mock.calls.at(-1)?.[0] as { sorting: { id: string; desc: boolean }[] };
      expect(last.sorting).toEqual([{ id, desc: false }]);
    });
  });
});
