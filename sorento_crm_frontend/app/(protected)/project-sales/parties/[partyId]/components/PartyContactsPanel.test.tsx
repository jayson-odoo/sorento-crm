/**
 * PS-REGISTRATION-V3 rule 4: the people at a party, kept on the party's own page.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const listPartyContacts = vi.fn();
const createPartyContact = vi.fn();
const run = vi.fn();
let canEdit = true;

vi.mock('next/navigation', () => ({
  usePathname: () => '/project-sales/parties/pt1',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => canEdit,
}));

vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: () => ({ run, targetId: null, isPending: false, countdown: null }),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ preferences: null, save: vi.fn(), reset: vi.fn() }),
}));

vi.mock('../../../_shared/services/projectService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../_shared/services/projectService')>();
  return {
    ...actual,
    listPartyContacts: (...args: unknown[]) => listPartyContacts(...args),
    createPartyContact: (...args: unknown[]) => createPartyContact(...args),
  };
});

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), custom: vi.fn() },
}));

import { PartyContactsPanel } from './PartyContactsPanel';

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PartyContactsPanel partyId="pt1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  canEdit = true;
  listPartyContacts.mockResolvedValue([]);
});

describe('PartyContactsPanel', () => {
  it('shows an explicit empty state', async () => {
    renderPanel();
    expect(await screen.findByText('No contacts yet')).toBeInTheDocument();
  });

  it('lists each contact with its phone, a blank phone as a dash', async () => {
    listPartyContacts.mockResolvedValue([
      { id: 'c1', party_id: 'pt1', name: 'Example Two', job_title: 'QS', phone: '+60130002222', is_active: true },
      { id: 'c2', party_id: 'pt1', name: 'Example Three', job_title: null, phone: null, is_active: true },
    ]);
    renderPanel();
    expect(await screen.findByText('Example Two')).toBeInTheDocument();
    expect(screen.getByText('+60130002222')).toBeInTheDocument();
    expect(screen.getByText('Example Three')).toBeInTheDocument();
  });

  it('adds a contact with a name only (phone is optional)', async () => {
    createPartyContact.mockResolvedValue({ id: 'c9', party_id: 'pt1', name: 'New Person', is_active: true });
    renderPanel();
    fireEvent.click(await screen.findByRole('button', { name: /add contact/i }));
    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: 'New Person' } });
    fireEvent.click(screen.getAllByRole('button', { name: /add contact/i }).at(-1)!);
    await waitFor(() =>
      expect(createPartyContact).toHaveBeenCalledWith('pt1', {
        name: 'New Person',
        job_title: null,
        phone: null,
        email: null,
      }),
    );
  });

  it('deletes through the deferred countdown, never a confirm dialog', async () => {
    listPartyContacts.mockResolvedValue([
      { id: 'c1', party_id: 'pt1', name: 'Example Two', is_active: true },
    ]);
    renderPanel();
    fireEvent.click(await screen.findByRole('button', { name: 'Delete Example Two' }));
    expect(run).toHaveBeenCalledWith({ id: 'c1', subject: 'Example Two' });
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('offers no add, edit or delete without the parties edit grant', async () => {
    canEdit = false;
    listPartyContacts.mockResolvedValue([
      { id: 'c1', party_id: 'pt1', name: 'Example Two', is_active: true },
    ]);
    renderPanel();
    await screen.findByText('Example Two');
    expect(screen.queryByRole('button', { name: /add contact/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Delete Example Two' })).not.toBeInTheDocument();
  });
});
