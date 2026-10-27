/**
 * GRID-DRAG-SELECT (owner Q4/Q5, 28 Oct): Internal Users gets Odoo's "select every matching
 * record": tick the header (this page), then the banner link ticks every contact matching the
 * filters, capped at 1,000 (the list endpoint's max page). The ids land in the ordinary
 * selection, so every existing bulk action works unchanged.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, within, waitFor } from '@testing-library/react';
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

const setOneMutate = vi.fn();
const setBulkMutate = vi.fn();
vi.mock('@/hooks/useRespondContactOutbound', () => ({
  RESPOND_CONTACTS_OUTBOUND_KEY: 'respond-contacts-outbound',
  useRespondContactOutboundMutations: () => ({
    setOne: { mutate: setOneMutate, isPending: false },
    setBulk: { mutate: setBulkMutate, isPending: false },
  }),
}));

vi.mock('@/components/contacts/PortalLinkButton', () => ({ default: () => null }));
vi.mock('@/services/contactImpersonationService', () => ({
  startContactImpersonation: vi.fn(),
}));

vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { email: 'admin@zzt.test' } } }),
}));
vi.mock('@/lib/is-superadmin', () => ({ isSuperadminUser: () => false }));

const permsRef = vi.hoisted(() => ({ view: true, add: true, edit: true }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => {
    if (slug === 'user_management.users.view') return permsRef.view;
    if (slug === 'user_management.users.add') return permsRef.add;
    if (slug === 'user_management.contacts.edit') return permsRef.edit;
    return false;
  },
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => '/user-management/contacts',
  useSearchParams: () => ({ get: () => null }),
}));

const toastError = vi.hoisted(() => vi.fn());
const generateExcelFileMock = vi.hoisted(() => vi.fn());
vi.mock('@/lib/excel-utils', async (orig) => ({
  ...(await orig<typeof import('@/lib/excel-utils')>()),
  generateExcelFile: (...a: unknown[]) => generateExcelFileMock(...a),
}));

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: toastError, warning: vi.fn() } }));


// The bulk dialogs are not under test: each one just reports how many contacts it was handed.
vi.mock('./BulkTagDialog', () => ({
  default: ({ targetContacts }: { targetContacts: unknown[] }) => (
    <div role="dialog">Tag dialog for {targetContacts.length} contacts</div>
  ),
}));

const contact = (n: number) => ({
  id: `c-${n}`,
  phone_number: `+6010000${String(n).padStart(4, '0')}`,
  name: `Demo Contact ${n}`,
  first_name: 'Demo',
  last_name: `Contact ${n}`,
  respond_io_id: `${100000 + n}`,
  outbound_enabled: true,
  access_type_codes: [],
  access_types: [],
  created_at: '2026-01-05T02:00:00',
  updated_at: '2026-01-05T02:00:00',
  linked_user_id: null,
  linked_user_name: null,
});

const PAGE = [1, 2, 3].map(contact);
let total = 1248;

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
  total = 1248;
  getContactsMock.mockImplementation(async (params: { pageSize: number }) =>
    params.pageSize === 1000
      ? { data: Array.from({ length: Math.min(total, 1000) }, (_, i) => contact(i + 1)), pagination: { total } }
      : { data: PAGE, pagination: { total } },
  );
  apiFetchMock.mockResolvedValue({ ok: true, json: async () => [] } as unknown as Response);
});

afterEach(() => cleanup());

const waitForRows = () => screen.findByLabelText(/outbound for Demo Contact 3/i);
const headerBox = () => screen.getByRole('checkbox', { name: 'Select all rows on this page' });

async function openActions() {
  const trigger = screen.getByRole('button', { name: /^actions$/i });
  trigger.focus();
  fireEvent.keyDown(trigger, { key: 'ArrowDown', code: 'ArrowDown' });
  return screen.findByRole('menu');
}

describe('Internal Users: select every matching contact (Odoo pattern, capped at 1,000)', () => {
  it('after the header tick, offers "Select first 1,000 of 1,248"', async () => {
    renderList();
    await waitForRows();
    fireEvent.click(headerBox());

    expect(screen.getByText('3 selected')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Select first 1,000 of 1,248' })).toBeInTheDocument();
  });

  it('says "Select all N records" when every match fits under the cap', async () => {
    total = 120;
    renderList();
    await waitForRows();
    fireEvent.click(headerBox());

    expect(screen.getByRole('button', { name: 'Select all 120 records' })).toBeInTheDocument();
  });

  it('fetches the matching contacts with the list filters and sort, and ticks them', async () => {
    renderList();
    await waitForRows();
    fireEvent.click(headerBox());
    fireEvent.click(screen.getByRole('button', { name: 'Select first 1,000 of 1,248' }));

    expect(await screen.findByText('First 1,000 of 1,248 matching records are selected.')).toBeInTheDocument();
    expect(screen.getByText('1,000 selected')).toBeInTheDocument();
    const call = getContactsMock.mock.calls.find(([p]) => (p as { pageSize: number }).pageSize === 1000)!;
    const [pageCall] = getContactsMock.mock.calls[0];
    expect(call[0]).toMatchObject({ pageIndex: 0, pageSize: 1000, sorting: (pageCall as { sorting: unknown }).sorting });
    expect(call[1]).toEqual(getContactsMock.mock.calls[0][1]);
  });

  it('bulk actions act on all 1,000, not the page', async () => {
    renderList();
    await waitForRows();
    fireEvent.click(headerBox());
    fireEvent.click(screen.getByRole('button', { name: 'Select first 1,000 of 1,248' }));
    await screen.findByText('1,000 selected');

    const menu = await openActions();
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Add tag (1000)' }));
    expect(await screen.findByText('Tag dialog for 1000 contacts')).toBeInTheDocument();
  });

  it('changing a tick leaves the all-matching mode and keeps only this page\'s ticks', async () => {
    renderList();
    await waitForRows();
    fireEvent.click(headerBox());
    fireEvent.click(screen.getByRole('button', { name: 'Select first 1,000 of 1,248' }));
    await screen.findByText('1,000 selected');

    const row2 = screen.getByLabelText(/outbound for Demo Contact 2/i).closest('tr')!;
    fireEvent.click(within(row2).getByRole('checkbox'));

    expect(screen.getByText('2 selected')).toBeInTheDocument();
    expect(screen.queryByText(/matching records are selected/)).toBeNull();
    const menu = await openActions();
    expect(within(menu).getByRole('menuitem', { name: 'Add tag (2)' })).toBeInTheDocument();
  });

  it('Clear selection leaves the mode and unticks everything', async () => {
    renderList();
    await waitForRows();
    fireEvent.click(headerBox());
    fireEvent.click(screen.getByRole('button', { name: 'Select first 1,000 of 1,248' }));
    await screen.findByText('1,000 selected');

    fireEvent.click(screen.getByRole('button', { name: 'Clear selection' }));
    expect(screen.queryByText(/\d selected/)).toBeNull();
    expect(screen.queryByText(/matching records are selected/)).toBeNull();
  });

  it('a failed fetch says so and leaves the page selection as it was', async () => {
    renderList();
    await waitForRows();
    getContactsMock.mockRejectedValueOnce(new Error('Server unavailable'));
    fireEvent.click(headerBox());
    fireEvent.click(screen.getByRole('button', { name: 'Select first 1,000 of 1,248' }));

    await waitFor(() => expect(toastError).toHaveBeenCalledWith('Server unavailable'));
    expect(screen.getByText('3 selected')).toBeInTheDocument();
  });

  it('Export hands the xlsx builder all 1,000 selected contacts, not the page\'s 3', async () => {
    renderList();
    await waitForRows();
    fireEvent.click(headerBox());
    fireEvent.click(screen.getByRole('button', { name: 'Select first 1,000 of 1,248' }));
    await screen.findByText('1,000 selected');

    const menu = await openActions();
    fireEvent.click(within(menu).getByRole('menuitem', { name: /^Export/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Download Excel' }));

    await waitFor(() => expect(generateExcelFileMock).toHaveBeenCalled());
    const rows = generateExcelFileMock.mock.calls[0][0] as Record<string, unknown>[];
    expect(rows).toHaveLength(1000);
    expect(rows.some((r) => Object.values(r).includes('Contact 1000'))).toBe(true);
  });
});
