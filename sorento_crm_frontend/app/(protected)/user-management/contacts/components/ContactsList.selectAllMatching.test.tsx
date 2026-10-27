/**
 * GRID-DRAG-SELECT (owner Q4/Q5, 28 Oct): Contacts gets Odoo's "select every matching
 * record": tick the header (this page), then the banner link ticks every contact matching the
 * filters, capped at 1,000 (the list endpoint's max page). The ids land in the ordinary
 * selection, so every existing bulk action works unchanged.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, render, screen, fireEvent, cleanup, within, waitFor } from '@testing-library/react';
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

const nav = vi.hoisted(() => ({ search: '' }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => '/user-management/contacts',
  useSearchParams: () => new URLSearchParams(nav.search),
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

// The link dialog is not under test: its success path just reports every contact as linked.
vi.mock('./BulkLinkCustomersDialog', () => ({
  default: ({
    open,
    contacts,
    onLinked,
  }: {
    open: boolean;
    contacts: { id: string }[];
    onLinked: (ids: string[]) => void;
  }) =>
    open ? (
      <>
        <button type="button" onClick={() => onLinked(contacts.map((c) => c.id))}>
          Finish link
        </button>
        <button type="button" onClick={() => onLinked(contacts.slice(0, 990).map((c) => c.id))}>
          Finish partial link
        </button>
      </>
    ) : null,
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
  const ui = () => (
    <QueryClientProvider client={client}>
      <ContactsList />
    </QueryClientProvider>
  );
  const view = render(ui());
  return { ...view, rerenderList: () => view.rerender(ui()) };
}

beforeEach(() => {
  vi.clearAllMocks();
  total = 1248;
  nav.search = '';
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

describe('Contacts: select every matching contact (Odoo pattern, capped at 1,000)', () => {
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
    expect(screen.getByRole('button', { name: 'Select first 1,000 of 1,248' })).toBeEnabled();
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

  const mouse = { pointerType: 'mouse', button: 0, buttons: 1, isPrimary: true, pointerId: 1 };
  const rowBox = (n: number) =>
    within(screen.getByLabelText(new RegExp(`outbound for Demo Contact ${n}$`, 'i')).closest('tr')!).getByRole('checkbox');
  const pageBigFetches = () =>
    getContactsMock.mock.calls.filter(([p]) => (p as { pageSize: number }).pageSize === 1000);

  async function enterMode() {
    const view = renderList();
    await waitForRows();
    fireEvent.click(headerBox());
    fireEvent.click(screen.getByRole('button', { name: 'Select first 1,000 of 1,248' }));
    await screen.findByText('1,000 selected');
    return view;
  }

  it('R1: a drag that unticks the page rows leaves no hidden selection', async () => {
    await enterMode();
    fireEvent.pointerDown(rowBox(1), mouse);
    fireEvent.pointerMove(rowBox(2), mouse);
    fireEvent.pointerMove(rowBox(3), mouse);
    fireEvent.pointerUp(window, mouse);
    fireEvent.click(rowBox(3).closest('tbody')!);

    expect(screen.queryByText(/\d+ selected/)).toBeNull();
    expect(screen.queryByText(/matching records are selected/)).toBeNull();
    fireEvent.click(rowBox(1));
    expect(screen.getByText('1 selected')).toBeInTheDocument();
    const menu = await openActions();
    expect(within(menu).getByRole('menuitem', { name: 'Delete (1)' })).toBeInTheDocument();
  });

  it('R2: a second click on the link while the first fetch is pending fires no second fetch', async () => {
    renderList();
    await waitForRows();
    getContactsMock.mockImplementationOnce(() => new Promise(() => {}));
    fireEvent.click(headerBox());
    fireEvent.click(screen.getByRole('button', { name: 'Select first 1,000 of 1,248' }));
    const again = await screen.findByRole('button', { name: 'Selecting...' });
    expect(again).toBeDisabled();
    fireEvent.click(again);
    expect(pageBigFetches()).toHaveLength(1);
  });

  it('R2: unticking while the fetch is pending, then it resolves: nothing is selected', async () => {
    renderList();
    await waitForRows();
    let resolve!: (v: unknown) => void;
    getContactsMock.mockImplementationOnce(() => new Promise((r) => (resolve = r)));
    fireEvent.click(headerBox());
    fireEvent.click(screen.getByRole('button', { name: 'Select first 1,000 of 1,248' }));
    // the user unticks the page while the fetch is out
    fireEvent.click(headerBox());
    expect(screen.queryByText(/\d+ selected/)).toBeNull();
    await act(async () => {
      resolve({ data: Array.from({ length: 1000 }, (_, i) => contact(i + 1)), pagination: { total } });
    });
    expect(screen.queryByText(/matching records are selected/)).toBeNull();
    expect(screen.queryByText('1,000 selected')).toBeNull();
  });

  it('R2: a sort change during the fetch discards the old result', async () => {
    nav.search = 'sort=last_name&dir=asc';
    const view = renderList();
    await waitForRows();
    let resolve!: (v: unknown) => void;
    getContactsMock.mockImplementationOnce(() => new Promise((r) => (resolve = r)));
    fireEvent.click(headerBox());
    fireEvent.click(screen.getByRole('button', { name: 'Select first 1,000 of 1,248' }));

    nav.search = 'sort=first_name&dir=asc';
    view.rerenderList();
    // the sort really changed: the list refetched on it
    await waitFor(() =>
      expect(
        getContactsMock.mock.calls.some(([p]) => JSON.stringify((p as { sorting: unknown }).sorting) === '[{"id":"first_name","desc":false}]'),
      ).toBe(true),
    );
    await act(async () => {
      resolve({ data: Array.from({ length: 1000 }, (_, i) => contact(i + 1)), pagination: { total } });
    });
    expect(screen.queryByText(/matching records are selected/)).toBeNull();
    expect(screen.queryByText('1,000 selected')).toBeNull();
  });

  it('R3: the 1,000-row fetch carries the list\'s non-default search, filter and sort', async () => {
    nav.search = 'query=zed&sort=last_name&dir=asc&chatbot_memory_level=own';
    renderList();
    await waitForRows();
    fireEvent.click(headerBox());
    fireEvent.click(screen.getByRole('button', { name: 'Select first 1,000 of 1,248' }));
    await screen.findByText('1,000 selected');

    const [params, filters] = pageBigFetches()[0];
    expect(params).toMatchObject({
      pageIndex: 0,
      pageSize: 1000,
      searchQuery: 'zed',
      sorting: [{ id: 'last_name', desc: false }],
    });
    expect(filters).toEqual({ chatbot_memory_level: 'own' });
  });

  it('R4: changing the search in the mode clears the banner and every tick', async () => {
    const view = await enterMode();
    // the search box is hidden by the bulk strip, so the change arrives as the list's own URL state
    nav.search = 'query=zed';
    view.rerenderList();
    await waitFor(() =>
      expect(getContactsMock.mock.calls.some(([p]) => (p as { searchQuery?: string }).searchQuery === 'zed')).toBe(true),
    );
    await waitFor(() => expect(screen.queryByText(/matching records are selected/)).toBeNull());
    expect(screen.queryByText(/\d+ selected/)).toBeNull();
  });

  it('R5: after Link customers succeeds on all of them, the strip and banner are gone', async () => {
    await enterMode();
    const menu = await openActions();
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Link customers (1000)' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Finish link' }));

    expect(screen.queryByText('1,000 selected')).toBeNull();
    expect(screen.queryByText(/matching records are selected/)).toBeNull();
  });

  it('S1: a partial Link customers success leaves the mode and counts no hidden remainder', async () => {
    await enterMode();
    const menu = await openActions();
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Link customers (1000)' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Finish partial link' }));

    expect(screen.queryByText('1,000 selected')).toBeNull();
    expect(screen.queryByText(/matching records are selected/)).toBeNull();
    const trigger = screen.queryByRole('button', { name: /^actions$/i });
    if (trigger) {
      const m = await openActions();
      expect(within(m).queryByRole('menuitem', { name: 'Add tag (10)' })).toBeNull();
    }
  });

  it('shows "Selecting..." (disabled) while the fetch is out, then the 1,000 selected badge', async () => {
    renderList();
    await waitForRows();
    let resolve!: (v: unknown) => void;
    getContactsMock.mockImplementationOnce(() => new Promise((r) => (resolve = r)));
    fireEvent.click(headerBox());
    fireEvent.click(screen.getByRole('button', { name: 'Select first 1,000 of 1,248' }));

    expect(await screen.findByRole('button', { name: 'Selecting...' })).toBeDisabled();
    await act(async () => {
      resolve({ data: Array.from({ length: 1000 }, (_, i) => contact(i + 1)), pagination: { total } });
    });
    expect(await screen.findByText('1,000 selected')).toBeInTheDocument();
  });

  it('P1: leaving the mode while the fetch is out frees the link at once', async () => {
    renderList();
    await waitForRows();
    getContactsMock.mockImplementationOnce(() => new Promise(() => {}));
    fireEvent.click(headerBox());
    fireEvent.click(screen.getByRole('button', { name: 'Select first 1,000 of 1,248' }));
    await screen.findByRole('button', { name: 'Selecting...' });

    fireEvent.click(headerBox());
    fireEvent.click(headerBox());
    expect(screen.getByRole('button', { name: 'Select first 1,000 of 1,248' })).toBeEnabled();
  });

  it('P1: a sort change while the fetch is out frees the link at once', async () => {
    nav.search = 'sort=last_name&dir=asc';
    const view = renderList();
    await waitForRows();
    getContactsMock.mockImplementationOnce(() => new Promise(() => {}));
    fireEvent.click(headerBox());
    fireEvent.click(screen.getByRole('button', { name: 'Select first 1,000 of 1,248' }));
    await screen.findByRole('button', { name: 'Selecting...' });

    nav.search = 'sort=first_name&dir=asc';
    view.rerenderList();
    await waitFor(() =>
      expect(
        getContactsMock.mock.calls.some(([p]) => JSON.stringify((p as { sorting: unknown }).sorting) === '[{"id":"first_name","desc":false}]'),
      ).toBe(true),
    );
    await waitForRows();
    if (!screen.queryByRole('button', { name: 'Select first 1,000 of 1,248' })) {
      fireEvent.click(headerBox());
      if (screen.queryByText(/\d+ selected/) && !screen.queryByRole('button', { name: /Select first|Selecting/ })) {
        fireEvent.click(headerBox());
      }
    }
    expect(screen.getByRole('button', { name: 'Select first 1,000 of 1,248' })).toBeEnabled();
  });
});
