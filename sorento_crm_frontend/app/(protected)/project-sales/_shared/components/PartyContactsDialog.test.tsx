/**
 * QUOTE-ATTN-PICKER (owner feedback 11 Nov): the contacts popup behind every Attn picker uses the
 * standard SearchableMultiSelect (search + "Select all (N)"), and while a contact is being added
 * its "Add contact" is the only primary action: Done/Cancel stay hidden so a half-typed contact
 * cannot be lost. Plan: documentation/plans/project-sales/PLAN-quote-attn-picker-11nov.md.
 * Names and numbers are invented.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { PartyContact } from '../types/project.types';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const listPartyContacts = vi.fn();
const createPartyContact = vi.fn();
vi.mock('../services/projectService', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../services/projectService')>();
  return {
    ...actual,
    listPartyContacts: (...a: unknown[]) => listPartyContacts(...a),
    createPartyContact: (...a: unknown[]) => createPartyContact(...a),
  };
});

import { PartyContactsDialog } from './PartyContactsDialog';

const CONTACTS: PartyContact[] = [
  {
    id: 'c-1',
    party_id: 'p-1',
    name: 'MR. CONTOH SATU',
    job_title: 'PM',
    phone: '+60120000001',
    is_active: true,
  },
  {
    id: 'c-2',
    party_id: 'p-1',
    name: 'EN. CONTOH DUA',
    phone: '+60120000002',
    is_active: true,
  },
  {
    id: 'c-3',
    party_id: 'p-1',
    name: 'PN. CONTOH TIGA',
    phone: null,
    is_active: true,
  },
];

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function renderDialog(
  over: Partial<React.ComponentProps<typeof PartyContactsDialog>> = {},
) {
  const props: React.ComponentProps<typeof PartyContactsDialog> = {
    title: (name) => `Attn at ${name}`,
    parties: [{ partyId: 'p-1', name: 'CONTOH SDN BHD' }],
    picks: { 'p-1': [] },
    canEdit: true,
    onSave: vi.fn(),
    onClose: vi.fn(),
    ...over,
  };
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <PartyContactsDialog {...props} />
    </QueryClientProvider>,
  );
  return props;
}

async function openPicker() {
  const dialog = await screen.findByRole('dialog');
  const trigger = await within(dialog).findByRole('combobox', {
    name: 'Contacts',
  });
  fireEvent.click(trigger);
  return dialog;
}

const selectAll = () =>
  document.querySelector<HTMLButtonElement>(
    '[data-slot="searchable-multi-select-all"]',
  );

describe('Attn contacts popup uses the standard multi-select', () => {
  it('offers search and Select all over the party contacts, one line each with the phone', async () => {
    listPartyContacts.mockResolvedValue(CONTACTS);
    renderDialog();
    await openPicker();
    expect(screen.getByPlaceholderText('Search...')).toBeInTheDocument();
    await waitFor(() =>
      expect(selectAll()?.textContent).toContain('Select all (3)'),
    );
    const row = screen.getByRole('option', { name: /MR\. CONTOH SATU/ });
    expect(row).toHaveTextContent('012-000 0001');
  });

  it('Select all then Done saves every contact', async () => {
    listPartyContacts.mockResolvedValue(CONTACTS);
    const props = renderDialog();
    const dialog = await openPicker();
    await waitFor(() => expect(selectAll()).toBeTruthy());
    fireEvent.click(selectAll()!);
    fireEvent.click(within(dialog).getByRole('button', { name: 'Done' }));
    expect(props.onSave).toHaveBeenCalledWith({ 'p-1': ['c-1', 'c-2', 'c-3'] });
  });

  it('a contact already on the project stays ticked and cannot be unticked', async () => {
    listPartyContacts.mockResolvedValue(CONTACTS);
    renderDialog({ fixed: { 'p-1': ['c-2'] } });
    await openPicker();
    const row = await screen.findByRole('option', { name: /EN\. CONTOH DUA/ });
    expect(row).toHaveAttribute('aria-checked', 'true');
    expect(row).toHaveAttribute('aria-disabled', 'true');
    expect(row).toHaveTextContent('On this project');
  });
});

describe('adding a contact is the only CTA while its form is open', () => {
  it('hides Done and Cancel while the add form is open', async () => {
    listPartyContacts.mockResolvedValue(CONTACTS);
    renderDialog();
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(
      await within(dialog).findByRole('button', { name: '+ Add contact' }),
    );
    expect(
      within(dialog).queryByRole('button', { name: 'Done' }),
    ).not.toBeInTheDocument();
    expect(
      within(dialog).getByRole('button', { name: 'Add contact' }),
    ).toBeInTheDocument();
  });

  it('cancelling the add form brings Done back with nothing added', async () => {
    listPartyContacts.mockResolvedValue(CONTACTS);
    const props = renderDialog();
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(
      await within(dialog).findByRole('button', { name: '+ Add contact' }),
    );
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Done' }));
    expect(createPartyContact).not.toHaveBeenCalled();
    expect(props.onSave).toHaveBeenCalledWith({ 'p-1': [] });
  });

  it('adding a contact ticks it and Done comes back to save it', async () => {
    listPartyContacts.mockResolvedValue(CONTACTS);
    createPartyContact.mockResolvedValue({
      id: 'c-new',
      party_id: 'p-1',
      name: 'MS. BARU',
      is_active: true,
    });
    const props = renderDialog({ picks: { 'p-1': ['c-1'] } });
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(
      await within(dialog).findByRole('button', { name: '+ Add contact' }),
    );
    fireEvent.change(within(dialog).getByLabelText(/^Name/), {
      target: { value: 'MS. BARU' },
    });
    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Add contact' }),
    );
    const done = await within(dialog).findByRole('button', { name: 'Done' });
    fireEvent.click(done);
    expect(props.onSave).toHaveBeenCalledWith({ 'p-1': ['c-1', 'c-new'] });
  });
});
