/**
 * PROJECT-PARTY-ROLES PR 2 (mock v4 screen 4, owner approved 10 Nov): the proposal "To" is chosen
 * from the parties, the project's first; picking autoloads the block; a party not on the project
 * is added in a role; Attn is chosen in the contacts popup. Names are invented.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));

const listParties = vi.fn();
const listPartyContacts = vi.fn();
vi.mock('../../../_shared/services/projectService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../_shared/services/projectService')>();
  return {
    ...actual,
    listParties: (...a: unknown[]) => listParties(...a),
    listPartyContacts: (...a: unknown[]) => listPartyContacts(...a),
    getPartiesOnProject: async () => [
      { party_id: 'p-dev', party_type: 'developer', role: 'developer', name: 'PARAGON CONTOH SDN BHD', phone: '03-0001', contacts: [] },
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
// Renders what fetchOptions returns, grouped, and lets a test pick one.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    id,
    fetchOptions,
    options,
    onOptionChange,
    onChange,
  }: {
    id?: string;
    fetchOptions?: (q: string) => Promise<Opt[]>;
    options?: Opt[];
    onOptionChange?: (o: Opt | null) => void;
    onChange: (v: string) => void;
  }) => {
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
  it('offers the project parties first with their role, then the other parties', async () => {
    listParties.mockResolvedValue({ data: [OTHER, { id: 'p-arch', party_type: 'architect', name: 'ARKITEK CONTOH', is_active: true }] });
    wrap(<QuotationRecipientPicker projectId="pr1" value={{}} locked={false} onChange={vi.fn()} />);
    const list = await screen.findByTestId('quotation-recipient-party');
    await waitFor(() => expect(within(list).getAllByRole('button')).toHaveLength(3));
    const labels = within(list).getAllByRole('button').map((b) => b.textContent);
    expect(labels).toEqual([
      'On this project: PARAGON CONTOH SDN BHD (Developer)',
      'On this project: ARKITEK CONTOH (Architect)',
      'Other parties: PGB CONTOH SDN BHD (Main contractor)',
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
