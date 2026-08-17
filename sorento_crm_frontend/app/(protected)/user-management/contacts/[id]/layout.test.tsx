/**
 * Contact detail shell - pins the tabbed structure required by the
 * "View and Edit are the same layout (binding)" contract in CLAUDE.md.
 *
 * The shell must offer exactly four tabs, in order, each pointing at its own route:
 *
 *   Profile : /user-management/contacts/{id}
 *   Access  : /user-management/contacts/{id}/access
 *   Routing : /user-management/contacts/{id}/routing
 *   Chat    : /user-management/contacts/{id}/chat
 *
 * Plus the rules the single-page version broke:
 *   - Created / Updated are read-only metadata: header strip, never a tab body.
 *   - Editable values (phone number, workspace) stay on the Profile card the pencil
 *     opens, so the read view and the edit dialog show the same fields.
 *   - Prev/next record navigation is present, and keeps the tab the user is on.
 *
 * The layout reads through its hooks and contact service; only the network client
 * (`apiFetch`) is mocked, so nothing hits the network.
 */
import React, { Suspense } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ContactLayout from './layout';
import type { RespondContact } from '../types/contact.types';

const CURRENT_ID = '11111111-1111-4111-8111-111111111111';
const NEXT_ID = '22222222-2222-4222-8222-222222222222';

const CONTACT: RespondContact = {
  id: CURRENT_ID,
  phone_number: '60123456789',
  name: 'Aisyah Rahman',
  first_name: 'Aisyah',
  last_name: 'Rahman',
  respond_io_id: '900123',
  workspace_id: 'ws-1',
  workspace_name: 'Sorento Main',
  workspace_space_id: '4477',
  access_types: [],
  created_at: new Date('2026-01-05T02:00:00Z'),
  updated_at: new Date('2026-02-09T04:30:00Z'),
};

const h = vi.hoisted(() => ({
  push: vi.fn(),
  pathname: '',
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: h.push, back: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => h.pathname,
  useSearchParams: () => new URLSearchParams(''),
}));

// Container pulls SettingsProvider context this unit test does not need.
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/components/contacts/PortalLinkButton', () => ({
  default: () => <button type="button">Portal link</button>,
}));

vi.mock('../components/ContactDeleteDialog', () => ({
  default: () => null,
}));

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  apiFetch: vi.fn(async (url: string) => ({
    ok: true,
    status: 200,
    json: async () =>
      url.includes(CURRENT_ID)
        ? CONTACT
        : { data: [{ id: CURRENT_ID }, { id: NEXT_ID }], pagination: { total: 2 } },
  })),
}));

async function renderLayout(pathname: string) {
  h.pathname = pathname;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  await act(async () => {
    render(
      <QueryClientProvider client={client}>
        <Suspense fallback={<div>Loading route</div>}>
          <ContactLayout params={Promise.resolve({ id: CURRENT_ID })}>
            <div>Tab body</div>
          </ContactLayout>
        </Suspense>
      </QueryClientProvider>,
    );
  });
  // Tabs stay disabled until the record resolves, so nothing is clickable before this.
  await waitFor(() => expect(screen.getAllByRole('tab')[0]).not.toBeDisabled());
}

const tabNames = () => screen.getAllByRole('tab').map((t) => (t.textContent ?? '').trim());

beforeEach(() => {
  h.push.mockClear();
});

afterEach(() => cleanup());

describe('Contact detail shell - tabs', () => {
  it('renders exactly four tabs: Profile, Access, Routing, Chat', async () => {
    await renderLayout(`/user-management/contacts/${CURRENT_ID}`);
    expect(tabNames()).toEqual(['Profile', 'Access', 'Routing', 'Chat']);
  });

  it('sends each tab to its own route', async () => {
    await renderLayout(`/user-management/contacts/${CURRENT_ID}`);

    const base = `/user-management/contacts/${CURRENT_ID}`;
    const expected: Array<[string, string]> = [
      ['Profile', base],
      ['Access', `${base}/access`],
      ['Routing', `${base}/routing`],
      ['Chat', `${base}/chat`],
    ];

    for (const [name, path] of expected) {
      h.push.mockClear();
      fireEvent.click(screen.getByRole('tab', { name }));
      expect(h.push, `${name} tab should route to ${path}`).toHaveBeenCalledWith(path);
    }
  });

  it('opens on Profile for the base route', async () => {
    await renderLayout(`/user-management/contacts/${CURRENT_ID}`);
    expect(screen.getByRole('tab', { name: 'Profile' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });

  it('follows the pathname for a child route', async () => {
    await renderLayout(`/user-management/contacts/${CURRENT_ID}/routing`);

    expect(screen.getByRole('tab', { name: 'Routing' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(screen.getByRole('tab', { name: 'Profile' })).toHaveAttribute(
      'aria-selected',
      'false',
    );
  });

  it('renders the tab body it is given', async () => {
    await renderLayout(`/user-management/contacts/${CURRENT_ID}`);
    expect(screen.getByText('Tab body')).toBeInTheDocument();
  });
});

describe('Contact detail shell - header strip', () => {
  it('shows the identity and read-only record metadata outside the tab body', async () => {
    await renderLayout(`/user-management/contacts/${CURRENT_ID}`);

    const page = (document.body.textContent ?? '').replace(/\s+/g, ' ');
    expect(page).toContain('60123456789');
    expect(page).toContain('Respond.io ID');
    expect(page).toContain('Created At');
    expect(page).toContain('Updated At');
  });

  it('leaves the editable workspace field to the Profile tab body', async () => {
    await renderLayout(`/user-management/contacts/${CURRENT_ID}`);

    const page = (document.body.textContent ?? '').replace(/\s+/g, ' ');
    expect(page).not.toContain('Respond.io Workspace');
  });
});

describe('Contact detail shell - record navigation', () => {
  it('renders prev/next record navigation', async () => {
    await renderLayout(`/user-management/contacts/${CURRENT_ID}`);

    expect(screen.getByLabelText(/^Previous /i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Next /i)).toBeInTheDocument();
  });

  it('keeps the current tab when stepping to the next record', async () => {
    await renderLayout(`/user-management/contacts/${CURRENT_ID}/chat`);

    fireEvent.click(screen.getByLabelText(/^Next /i));

    expect(h.push).toHaveBeenCalledWith(`/user-management/contacts/${NEXT_ID}/chat`);
  });
});
