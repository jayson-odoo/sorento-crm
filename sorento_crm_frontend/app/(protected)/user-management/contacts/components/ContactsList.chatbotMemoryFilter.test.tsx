/**
 * S13 follow-up (reviewer finding, PR #1304): the Settings > Chatbot > Memory card's
 * "N contacts" count links to `/user-management/contacts?chatbot_memory_level=own` -
 * this pins the OTHER end, that the Contacts list actually reads that URL param and
 * sends it through to the list GET, through the existing service/hook layers
 * (`getContacts` -> `buildDataGridParams(params, extra)`), not a hand-rolled query
 * string. The backend filters to `chatbot_memory_level IS NOT NULL` for `own`.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ContactsList from './ContactsList';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({
  apiFetch: (...a: unknown[]) => apiFetch(...a),
}));

vi.mock('@/hooks/useRespondContactOutbound', () => ({
  RESPOND_CONTACTS_OUTBOUND_KEY: 'respond-contacts-outbound',
  useRespondContactOutboundMutations: () => ({
    setOne: { mutate: vi.fn(), isPending: false },
    setBulk: { mutate: vi.fn(), isPending: false },
  }),
}));

// main's #1306 made ContactsList read `users.view` / `users.add` and mount the
// "Add user" dialog, which reads the session even while closed; stubbed the same
// way ContactsList.test.tsx does, so no SessionProvider is needed here.
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { email: 'admin@zzt.test' } } }),
}));
vi.mock('@/lib/is-superadmin', () => ({ isSuperadminUser: () => false }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => false,
}));

vi.mock('@/components/contacts/PortalLinkButton', () => ({ default: () => null }));
vi.mock('@/services/contactImpersonationService', () => ({
  startContactImpersonation: vi.fn(),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

// The URL the "N contacts" link on the Memory settings card sends the reader to -
// a REAL `URLSearchParams` so `useListStateFromUrl`'s own `.toString()` read works
// the same way it does against the real `next/navigation` hook.
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => '/user-management/contacts',
  useSearchParams: () => new URLSearchParams('chatbot_memory_level=own'),
}));

function mockContacts() {
  apiFetch.mockResolvedValue({
    ok: true,
    json: async () => ({ data: [], pagination: { total: 0, page: 1, limit: 50 }, empty: true }),
  });
}

function renderWithClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ContactsList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  apiFetch.mockReset();
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
    }));
  }
  if (!('ResizeObserver' in window)) {
    (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => cleanup());

describe('ContactsList - reads chatbot_memory_level from the URL (S13 follow-up)', () => {
  it('sends chatbot_memory_level=own on the list GET when the page URL carries it', async () => {
    mockContacts();
    renderWithClient();

    await waitFor(() =>
      expect(
        apiFetch.mock.calls.some(
          (call) => String(call[0]).includes('/contacts?') && String(call[0]).includes('chatbot_memory_level'),
        ),
      ).toBe(true),
    );
  });
});
