/**
 * PROJECT-PARTY-ROLES PR 2 (mock v4 screen 4, owner approved 10 Nov): the proposal "To" is chosen
 * from the parties, the project's first; picking autoloads the block; a party not on the project
 * is added in a role; Attn is chosen in the contacts popup. Names are invented.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));

const listParties = vi.fn();
const listPartyContacts = vi.fn();
const createParty = vi.fn();
const updateParty = vi.fn();
vi.mock('../../../_shared/services/projectService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../_shared/services/projectService')>();
  return {
    ...actual,
    listParties: (...a: unknown[]) => listParties(...a),
    listPartyContacts: (...a: unknown[]) => listPartyContacts(...a),
    createParty: (...a: unknown[]) => createParty(...a),
    updateParty: (...a: unknown[]) => updateParty(...a),
    getPartiesOnProject: async () => [
      { party_id: 'p-dev', party_type: 'developer', role: 'developer', name: 'PARAGON CONTOH SDN BHD', phone: '03-0001', address: 'No 1, Jalan Paragon', email: 'info@paragon.example', contacts: [] },
      { party_id: 'p-arch', party_type: 'architect', role: 'architect', name: 'ARKITEK CONTOH', phone: null, contacts: [] },
    ],
    listPartyRoles: async () => [
      { value: 'developer', label: 'Developer', is_active: true, allows_many: false },
      { value: 'architect', label: 'Architect', is_active: true, allows_many: false },
      { value: 'main_contractor', label: 'Main contractor', is_active: true, allows_many: false },
      { value: 'trading_house', label: 'Trading house', is_active: true, allows_many: true },
    ],
  };
});

type Opt = { value: string; label: string; description?: string; group?: string };
const selectCreate: Record<string, ((q: string) => unknown) | undefined> = {};
// Renders what fetchOptions returns, grouped, and lets a test pick one.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    id,
    fetchOptions,
    options,
    onOptionChange,
    onChange,
    createOption,
  }: {
    id?: string;
    fetchOptions?: (q: string) => Promise<Opt[]>;
    options?: Opt[];
    onOptionChange?: (o: Opt | null) => void;
    onChange: (v: string) => void;
    createOption?: { onCreate: (q: string) => unknown };
  }) => {
    selectCreate[id ?? ''] = createOption?.onCreate;
    const [rows, setRows] = React.useState<Opt[]>(options ?? []);
    React.useEffect(() => {
      if (fetchOptions) void fetchOptions('').then(setRows);
    }, [fetchOptions]);
    return (
      <ul data-testid={id}>
        {rows.map((o) => (
          <li key={o.value}>
            <button
              type="button"
              onClick={() => {
                onChange(o.value);
                onOptionChange?.(o);
              }}
            >
              {o.group ? `${o.group}: ` : ''}
              {o.label}
              {o.description ? ` (${o.description})` : ''}
            </button>
          </li>
        ))}
      </ul>
    );
  },
}));

import { QuotationAttnChooser, QuotationRecipientPicker } from './QuotationRecipientPicker';

function wrap(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const OTHER = {
  id: 'p-pgb', party_type: 'main_contractor', name: 'PGB CONTOH SDN BHD', is_active: true,
  address: 'Level 8, Menara PGB', phone: '03-1111', email: 'info@pgb.example',
};

describe('the To party picker', () => {
  it('a party on the project autoloads its own address and email, even when the search misses it', async () => {
    listParties.mockResolvedValue({ data: [] });
    const onChange = vi.fn();
    wrap(<QuotationRecipientPicker projectId="pr1" siteAddress="Lot 1, Kuantan" value={{}} locked={false} onChange={onChange} />);
    fireEvent.click(await screen.findByRole('button', { name: /PARAGON CONTOH/ }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        recipient_party_id: 'p-dev',
        recipient_role: 'developer',
        recipient_address_snapshot: 'No 1, Jalan Paragon',
        recipient_phone_snapshot: '03-0001',
        recipient_email_snapshot: 'info@paragon.example',
      }),
    );
  });

  it('a party found by name only leaves its details to the server, never the site address', async () => {
    listParties.mockResolvedValue({ data: [{ id: 'p-x', party_type: 'consultant', name: 'NAMES ONLY CONTOH' }] });
    const onChange = vi.fn();
    wrap(<QuotationRecipientPicker projectId="pr1" siteAddress="Lot 1, Kuantan" value={{}} locked={false} onChange={onChange} />);
    fireEvent.click(await screen.findByRole('button', { name: /NAMES ONLY CONTOH/ }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        recipient_party_id: 'p-x',
        recipient_address_snapshot: null,
        recipient_phone_snapshot: null,
        recipient_email_snapshot: null,
      }),
    );
  });

  it('offers the project parties first with their role, then the other parties', async () => {
    listParties.mockResolvedValue({ data: [OTHER, { id: 'p-arch', party_type: 'architect', name: 'ARKITEK CONTOH', is_active: true }] });
    wrap(<QuotationRecipientPicker projectId="pr1" value={{}} locked={false} onChange={vi.fn()} />);
    const list = await screen.findByTestId('quotation-recipient-party');
    await waitFor(() => expect(within(list).getAllByRole('button')).toHaveLength(3));
    const labels = within(list).getAllByRole('button').map((b) => b.textContent);
    // One line per option (owner hand test 10 Nov): no role subtitle.
    expect(labels).toEqual([
      'On this project: PARAGON CONTOH SDN BHD',
      'On this project: ARKITEK CONTOH',
      'Other parties: PGB CONTOH SDN BHD',
    ]);
    expect(listParties).toHaveBeenCalledWith({ query: undefined, limit: 20 });
  });

  it('picking a party autoloads the block and keeps its role on the project', async () => {
    listParties.mockResolvedValue({ data: [] });
    const onChange = vi.fn();
    wrap(<QuotationRecipientPicker projectId="pr1" siteAddress="Lot 1, Kuantan" value={{}} locked={false} onChange={onChange} />);
    fireEvent.click(await screen.findByRole('button', { name: /ARKITEK CONTOH/ }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        recipient_party_id: 'p-arch',
        recipient_role: 'architect',
        recipient_name_snapshot: 'ARKITEK CONTOH',
        // No address on the party: the project's site address (owner Q7 a).
        recipient_address_snapshot: 'Lot 1, Kuantan',
        attn_name: null,
      }),
    );
  });

  it('a party not on the project autoloads its own details and asks for the role', async () => {
    listParties.mockResolvedValue({ data: [OTHER] });
    const onChange = vi.fn();
    const { rerender } = wrap(
      <QuotationRecipientPicker projectId="pr1" value={{}} locked={false} onChange={onChange} />,
    );
    fireEvent.click(await screen.findByRole('button', { name: /PGB CONTOH/ }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        recipient_party_id: 'p-pgb',
        recipient_role: 'main_contractor',
        recipient_address_snapshot: 'Level 8, Menara PGB',
        recipient_phone_snapshot: '03-1111',
        recipient_email_snapshot: 'info@pgb.example',
      }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    rerender(
      <QueryClientProvider client={client}>
        <QuotationRecipientPicker
          projectId="pr1"
          value={{ recipient_party_id: 'p-pgb', recipient_role: 'main_contractor', recipient_name_snapshot: 'PGB CONTOH SDN BHD' }}
          locked={false}
          onChange={onChange}
        />
      </QueryClientProvider>,
    );
    expect(await screen.findByText('Not on this project yet. Add as')).toBeInTheDocument();
    // A one-party role already filled on the project is not offered.
    const roles = within(screen.getByTestId('quotation-recipient-role')).getAllByRole('button').map((b) => b.textContent);
    expect(roles).toEqual(['Main contractor', 'Trading house']);
  });

  it('a party made in the picker takes the role it is added in as its usual role', async () => {
    listParties.mockResolvedValue({ data: [] });
    createParty.mockResolvedValue({ id: 'p-new', name: 'BARU CONTOH', party_type: 'main_contractor', is_active: true });
    updateParty.mockResolvedValue({ id: 'p-new', name: 'BARU CONTOH', party_type: 'trading_house', is_active: true });
    const onChange = vi.fn();
    const { rerender } = wrap(<QuotationRecipientPicker projectId="pr1" value={{}} locked={false} onChange={onChange} />);
    await screen.findByTestId('quotation-recipient-party');
    // The role list loads on its own query; create once it is there.
    await waitFor(async () => {
      await act(async () => {
        await selectCreate['quotation-recipient-party']!('BARU CONTOH');
      });
      expect(createParty).toHaveBeenCalled();
    });
    expect(createParty).toHaveBeenCalledWith(expect.objectContaining({ name: 'BARU CONTOH', party_type: 'main_contractor' }));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    rerender(
      <QueryClientProvider client={client}>
        <QuotationRecipientPicker
          projectId="pr1"
          value={{ recipient_party_id: 'p-new', recipient_role: 'main_contractor', recipient_name_snapshot: 'BARU CONTOH' }}
          locked={false}
          onChange={onChange}
        />
      </QueryClientProvider>,
    );
    fireEvent.click(await screen.findByRole('button', { name: 'Trading house' }));
    await waitFor(() => expect(updateParty).toHaveBeenCalledWith('p-new', { party_type: 'trading_house' }));
  });

  it('once issued, the party is shown and cannot be changed', async () => {
    wrap(
      <QuotationRecipientPicker
        projectId="pr1"
        value={{ recipient_party_id: 'p-dev', recipient_name_snapshot: 'PARAGON CONTOH SDN BHD' }}
        locked
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText('PARAGON CONTOH SDN BHD')).toBeInTheDocument();
    expect(screen.queryByTestId('quotation-recipient-party')).toBeNull();
  });
});

describe('Attn from the contacts popup', () => {
  it('two ticked contacts fill Attn joined with &, phone and email from the first', async () => {
    listPartyContacts.mockResolvedValue([
      { id: 'c1', party_id: 'p-pgb', name: 'MS. ANNE CONTOH', phone: '012-0001', email: 'anne@pgb.example', is_active: true },
      { id: 'c2', party_id: 'p-pgb', name: 'MS IIYANA CONTOH', phone: null, is_active: true },
    ]);
    const onChange = vi.fn();
    wrap(
      <QuotationAttnChooser
        value={{ recipient_party_id: 'p-pgb' }}
        partyName="PGB CONTOH SDN BHD"
        locked={false}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Choose contacts' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Attn at PGB CONTOH SDN BHD')).toBeInTheDocument();
    fireEvent.click(await within(dialog).findByLabelText(/MS\. ANNE CONTOH/));
    fireEvent.click(within(dialog).getByLabelText(/MS IIYANA CONTOH/));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Done' }));
    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith({
        attn_contact_ids: ['c1', 'c2'],
        attn_name: 'MS. ANNE CONTOH & MS IIYANA CONTOH',
        recipient_phone_snapshot: '012-0001',
        recipient_email_snapshot: 'anne@pgb.example',
      }),
    );
  });

  it('a contact without a number or email keeps the party ones the pick loaded', async () => {
    listPartyContacts.mockResolvedValue([
      { id: 'c2', party_id: 'p-pgb', name: 'MS IIYANA CONTOH', phone: null, email: null, is_active: true },
    ]);
    const onChange = vi.fn();
    wrap(
      <QuotationAttnChooser
        value={{ recipient_party_id: 'p-pgb', recipient_phone_snapshot: '03-1111', recipient_email_snapshot: 'info@pgb.example' }}
        partyName="PGB CONTOH SDN BHD"
        locked={false}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Choose contacts' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(await within(dialog).findByLabelText(/MS IIYANA CONTOH/));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Done' }));
    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({
          attn_name: 'MS IIYANA CONTOH',
          recipient_phone_snapshot: '03-1111',
          recipient_email_snapshot: 'info@pgb.example',
        }),
      ),
    );
  });

  it('a party with exactly one contact fills Attn with it straight away', async () => {
    listPartyContacts.mockResolvedValue([
      { id: 'c1', party_id: 'p-pgb', name: 'MS. ANNE CONTOH', phone: '012-0001', email: 'anne@pgb.example', is_active: true },
    ]);
    const onChange = vi.fn();
    wrap(
      <QuotationAttnChooser value={{ recipient_party_id: 'p-pgb' }} partyName="PGB" locked={false} autoPick onChange={onChange} />,
    );
    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({ attn_contact_ids: ['c1'], attn_name: 'MS. ANNE CONTOH' }),
      ),
    );
  });

  it('switching to another party and back re-applies the single contact (owner re-test 10 Nov)', async () => {
    listPartyContacts.mockImplementation(async (partyId: string) =>
      partyId === 'p-a'
        ? [{ id: 'ca', party_id: 'p-a', name: 'EN. AGROW', phone: '+60129876543', is_active: true }]
        : [
            { id: 'cb1', party_id: 'p-b', name: 'MS. B1', is_active: true },
            { id: 'cb2', party_id: 'p-b', name: 'MS. B2', is_active: true },
          ],
    );
    const onChange = vi.fn();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = (value: object, autoPick = true) => (
      <QueryClientProvider client={client}>
        <QuotationAttnChooser value={value} partyName="X" locked={false} autoPick={autoPick} onChange={onChange} />
      </QueryClientProvider>
    );
    const { rerender } = render(view({ recipient_party_id: 'p-a' }));
    await waitFor(() => expect(onChange).toHaveBeenCalledTimes(1));
    rerender(view({ recipient_party_id: 'p-b' }));
    await screen.findByRole('button', { name: 'Choose contacts' });
    rerender(view({ recipient_party_id: 'p-a' }));
    await waitFor(() => expect(onChange).toHaveBeenCalledTimes(2));
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ attn_contact_ids: ['ca'], attn_name: 'EN. AGROW', recipient_phone_snapshot: '012-987 6543' }),
    );
  });

  it('on a saved proposal, picking a party (even the saved one back) applies its single contact', async () => {
    listPartyContacts.mockImplementation(async (partyId: string) =>
      partyId === 'p-a' ? [{ id: 'ca', party_id: 'p-a', name: 'EN. AGROW', is_active: true }] : [],
    );
    const onChange = vi.fn();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = (value: object) => (
      <QueryClientProvider client={client}>
        <QuotationAttnChooser value={value} partyName="X" locked={false} onChange={onChange} />
      </QueryClientProvider>
    );
    const { rerender } = render(view({ recipient_party_id: 'p-a' }));
    await screen.findByRole('button', { name: 'Choose contacts' });
    await new Promise((r) => setTimeout(r, 30));
    expect(onChange).not.toHaveBeenCalled();
    rerender(view({ recipient_party_id: 'p-b' }));
    rerender(view({ recipient_party_id: 'p-a' }));
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ attn_contact_ids: ['ca'] })));
  });

  it('no automatic Attn on a saved proposal whose party did not change', async () => {
    listPartyContacts.mockResolvedValue([
      { id: 'c1', party_id: 'p-pgb', name: 'MS. ANNE CONTOH', phone: null, is_active: true },
    ]);
    const onChange = vi.fn();
    wrap(<QuotationAttnChooser value={{ recipient_party_id: 'p-pgb' }} partyName="PGB" locked={false} onChange={onChange} />);
    await screen.findByRole('button', { name: 'Choose contacts' });
    await new Promise((r) => setTimeout(r, 50));
    expect(onChange).not.toHaveBeenCalled();
  });

  it('is not offered before a party is picked, nor once issued', () => {
    const { rerender } = wrap(
      <QuotationAttnChooser value={{}} partyName="" locked={false} onChange={vi.fn()} />,
    );
    expect(screen.queryByRole('button', { name: 'Choose contacts' })).toBeNull();
    const client = new QueryClient();
    rerender(
      <QueryClientProvider client={client}>
        <QuotationAttnChooser value={{ recipient_party_id: 'p1' }} partyName="X" locked onChange={vi.fn()} />
      </QueryClientProvider>,
    );
    expect(screen.queryByRole('button', { name: 'Choose contacts' })).toBeNull();
  });
});
