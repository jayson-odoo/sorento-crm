/**
 * PROJECT-PARTY-ROLES (mock v4, owner approved 10 Nov): the Parties section is drawn from the
 * editable role list, one line per role; contacts are picked in a popup that only adds.
 * Card: documentation/plans/project-sales/CARD-project-party-roles-10nov.md. Names are invented.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { PartyContact, PartyRole } from '../types/project.types';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const listPartyContacts = vi.fn();
const createPartyContact = vi.fn();
const updatePartyContact = vi.fn();
const listParties = vi.fn();
vi.mock('../services/projectService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/projectService')>();
  return {
    ...actual,
    listPartyContacts: (...a: unknown[]) => listPartyContacts(...a),
    createPartyContact: (...a: unknown[]) => createPartyContact(...a),
    updatePartyContact: (...a: unknown[]) => updatePartyContact(...a),
    listParties: (...a: unknown[]) => listParties(...a),
    listPartyRoles: async () => ROLES,
  };
});

type Opt = { value: string; label: string };
// A static stand-in for the async pickers: lists what fetchOptions returns.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({ id, selectedOption }: { id?: string; selectedOption?: Opt }) => (
    <span data-testid={id}>{selectedOption?.label ?? ''}</span>
  ),
}));
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({ id, selectedOptions }: { id?: string; selectedOptions?: Opt[] }) => (
    <span data-testid={id} data-multi="true">
      {(selectedOptions ?? []).map((o) => o.label).join('|')}
    </span>
  ),
}));

const ROLES: PartyRole[] = [
  { value: 'developer', label: 'Developer', is_active: true, allows_many: false },
  { value: 'architect', label: 'Architect', is_active: true, allows_many: false },
  { value: 'main_contractor', label: 'Main con', is_active: true, allows_many: false },
  { value: 'trading_house', label: 'Trading house', is_active: true, allows_many: true },
  { value: 'interior_designer', label: 'Interior designer', is_active: false, allows_many: false },
  { value: 'quantity_surveyor', label: 'Quantity surveyor', is_active: true, allows_many: false },
];

const CONTACTS: PartyContact[] = [
  { id: 'c-1', party_id: 'p-mc', name: 'MR. CONTOH SATU', job_title: 'PM', phone: null, is_active: true },
  { id: 'c-2', party_id: 'p-mc', name: 'EN. CONTOH DUA', job_title: 'QS', phone: '0130000000', is_active: true },
  { id: 'c-3', party_id: 'p-mc', name: 'PN. CONTOH TIGA', phone: '0190000000', is_active: true },
];

import { ProjectPartiesSection, type PartyPick } from './ProjectPartiesSection';

function renderSection(over: Partial<React.ComponentProps<typeof ProjectPartiesSection>> = {}) {
  const props: React.ComponentProps<typeof ProjectPartiesSection> = {
    roles: ROLES,
    picks: {},
    onPicksChange: vi.fn(),
    contactPicks: {},
    onContactPicksChange: vi.fn(),
    canCreateParty: true,
    createParty: vi.fn(async () => null),
    ...over,
  };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ProjectPartiesSection {...props} />
    </QueryClientProvider>,
  );
  return props;
}

const MC: PartyPick = { value: 'p-mc', label: 'CONTOH BUILDERS BHD' };

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('Parties section from the role list', () => {
  it('shows one line per active role in list order, developer excluded, label as configured', () => {
    renderSection();
    const ids = Array.from(document.querySelectorAll('[data-testid^="project-party-"]')).map((el) =>
      el.getAttribute('data-testid'),
    );
    expect(ids).toEqual([
      'project-party-architect',
      'project-party-main-contractor',
      'project-party-trading-house',
      'project-party-quantity-surveyor',
    ]);
    expect(screen.getByText('Main con')).toBeInTheDocument();
    expect(screen.queryByText('Interior designer')).not.toBeInTheDocument();
  });

  it('a many-parties role gets the multi picker, a one-party role the single one', () => {
    renderSection();
    expect(screen.getByTestId('project-party-trading-house')).toHaveAttribute('data-multi', 'true');
    expect(screen.getByTestId('project-party-architect')).not.toHaveAttribute('data-multi');
  });

  it('an inactive role already on the project still shows, with an Inactive pill', () => {
    renderSection({ picks: { interior_designer: [{ value: 'p-id', label: 'CONTOH ID' }] } });
    expect(screen.getByTestId('project-party-interior-designer')).toHaveTextContent('CONTOH ID');
    expect(screen.getByText('Inactive')).toBeInTheDocument();
  });

  it('a one-party role holding two parties keeps both in a multi picker', () => {
    renderSection({
      picks: { architect: [{ value: 'a1', label: 'ARCH ONE' }, { value: 'a2', label: 'ARCH TWO' }] },
    });
    expect(screen.getByTestId('project-party-architect')).toHaveAttribute('data-multi', 'true');
  });

  it('has no separate "Contacts at" boxes', () => {
    renderSection({ picks: { main_contractor: [MC] } });
    expect(screen.queryByText(/Contacts at/)).not.toBeInTheDocument();
  });

  it('shows the contacts link only once a party is picked, with the count', () => {
    renderSection({
      picks: { main_contractor: [MC] },
      contactPicks: { 'p-mc': ['c-1'] },
      fixedContacts: { 'p-mc': ['c-3'] },
    });
    expect(screen.getByRole('button', { name: '2 contacts' })).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /contact/ })).toHaveLength(1);
  });

  it('shows the developer read-only with its own contacts link', () => {
    renderSection({ developer: { value: 'p-dev', label: 'CONTOH DEVELOPER BHD' } });
    expect(screen.getByText('CONTOH DEVELOPER BHD')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add contacts' })).toBeInTheDocument();
  });
});

describe('contacts popup', () => {
  it('ticks a contact and hands the picks back on Done', async () => {
    listPartyContacts.mockResolvedValue(CONTACTS);
    const props = renderSection({ picks: { main_contractor: [MC] } });
    fireEvent.click(screen.getByRole('button', { name: 'Add contacts' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Contacts at CONTOH BUILDERS BHD')).toBeInTheDocument();
    fireEvent.click(await within(dialog).findByLabelText(/EN\. CONTOH DUA/));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Done' }));
    expect(props.onContactPicksChange).toHaveBeenCalledWith({ 'p-mc': ['c-2'] });
  });

  it('a contact already on the project is ticked, fixed and marked', async () => {
    listPartyContacts.mockResolvedValue(CONTACTS);
    renderSection({ picks: { main_contractor: [MC] }, fixedContacts: { 'p-mc': ['c-3'] } });
    fireEvent.click(screen.getByRole('button', { name: '1 contact' }));
    const dialog = await screen.findByRole('dialog');
    const box = await within(dialog).findByRole('checkbox', { name: /PN\. CONTOH TIGA/ });
    expect(box).toBeChecked();
    expect(box).toBeDisabled();
    expect(within(dialog).getByText('On this project')).toBeInTheDocument();
  });

  it('adds a missing number to the contact in place', async () => {
    listPartyContacts.mockResolvedValue(CONTACTS);
    updatePartyContact.mockResolvedValue({ ...CONTACTS[0], phone: '0120000000' });
    renderSection({ picks: { main_contractor: [MC] } });
    fireEvent.click(screen.getByRole('button', { name: 'Add contacts' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(await within(dialog).findByRole('button', { name: 'Add number' }));
    fireEvent.change(within(dialog).getByLabelText('Phone for MR. CONTOH SATU'), {
      target: { value: '0120000000' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(updatePartyContact).toHaveBeenCalledWith('p-mc', 'c-1', { phone: '0120000000' }),
    );
  });

  it('creates a missing contact with only a name and ticks it', async () => {
    listPartyContacts.mockResolvedValue([]);
    createPartyContact.mockResolvedValue({ id: 'c-new', party_id: 'p-mc', name: 'MS. BARU', is_active: true });
    const props = renderSection({ picks: { main_contractor: [MC] } });
    fireEvent.click(screen.getByRole('button', { name: 'Add contacts' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(await within(dialog).findByRole('button', { name: '+ Add contact' }));
    fireEvent.change(within(dialog).getByLabelText(/Name/), { target: { value: 'MS. BARU' } });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add contact' }));
    await waitFor(() =>
      expect(createPartyContact).toHaveBeenCalledWith('p-mc', { name: 'MS. BARU', job_title: null, phone: null }),
    );
    fireEvent.click(within(dialog).getByRole('button', { name: 'Done' }));
    expect(props.onContactPicksChange).toHaveBeenCalledWith({ 'p-mc': ['c-new'] });
  });

  it('without the parties edit grant the popup only picks', async () => {
    listPartyContacts.mockResolvedValue(CONTACTS);
    renderSection({ picks: { main_contractor: [MC] }, canCreateParty: false });
    fireEvent.click(screen.getByRole('button', { name: 'Add contacts' }));
    const dialog = await screen.findByRole('dialog');
    await within(dialog).findByText('MR. CONTOH SATU');
    expect(within(dialog).queryByRole('button', { name: '+ Add contact' })).not.toBeInTheDocument();
    expect(within(dialog).queryByRole('button', { name: 'Add number' })).not.toBeInTheDocument();
  });

  it('a many-parties role shows one tab per picked party', async () => {
    listPartyContacts.mockResolvedValue([]);
    renderSection({
      picks: {
        trading_house: [
          { value: 'th-a', label: 'TRADING A' },
          { value: 'th-b', label: 'TRADING B' },
        ],
      },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Add contacts' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('tab', { name: 'TRADING A' })).toBeInTheDocument();
    expect(within(dialog).getByRole('tab', { name: 'TRADING B' })).toBeInTheDocument();
  });
});
