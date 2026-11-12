/** F4 / F5: the add and edit form. Services mocked; the dialog, hooks and rows are real. */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render as rtlRender, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DealerAccessGrantError, type DealerAccessRow } from '@/services/dealerAccessService';
import DealerAccessFormDialog from './DealerAccessFormDialog';

function render(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtlRender(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }));
vi.mock('@/lib/toast', () => ({ toast }));

const svc = vi.hoisted(() => ({
  getAccounts: vi.fn(),
  grant: vi.fn(),
  updatePerson: vi.fn(),
}));
vi.mock('@/services/dealerAccessService', async (orig) => ({
  ...(await orig<typeof import('@/services/dealerAccessService')>()),
  getAccounts: svc.getAccounts,
  grant: svc.grant,
  updatePerson: svc.updatePerson,
}));

vi.mock('../hooks/useMyDealerCompanies', () => ({
  useMyDealerCompanies: () => ({
    options: [{ value: 'SRT', label: 'Sorento' }],
    isLoading: false,
  }),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    value: string;
    onChange: (v: string) => void;
    options?: { value: string; label: string }[];
  }) => (
    <select id={props.id} value={props.value} onChange={(e) => props.onChange(e.target.value)}>
      {(props.options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: (props: {
    id?: string;
    value: string[];
    onChange: (v: string[]) => void;
    options?: { value: string; label: string }[];
  }) => (
    <select
      id={props.id}
      multiple
      value={props.value}
      onChange={(e) => props.onChange(Array.from(e.target.selectedOptions).map((o) => o.value))}
    >
      {(props.options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));
vi.mock('@/components/common/PhoneInput', () => ({
  PhoneInput: (props: {
    id?: string;
    value: string;
    onChange: (v: string, meta: { valid: boolean; country: string }) => void;
  }) => (
    <input
      id={props.id}
      aria-label={props.id}
      value={props.value}
      onChange={(e) => props.onChange(e.target.value, { valid: true, country: 'MY' })}
    />
  ),
}));

const ACCOUNTS = [
  { id: 'a1', code: '300-N034', name: 'CHO*** (A/C I)' },
  { id: 'a2', code: '300-N035', name: 'CHO*** (A/C II)' },
];

beforeEach(() => {
  vi.clearAllMocks();
  svc.getAccounts.mockResolvedValue(ACCOUNTS);
});

describe('DealerAccessFormDialog - add', () => {
  it('shows a refused row under that row and keeps what was typed', async () => {
    svc.grant.mockRejectedValue(
      new DealerAccessGrantError('Some people were refused.', {
        1: 'This number belongs to a staff member.',
      }),
    );
    render(<DealerAccessFormDialog open onOpenChange={vi.fn()} />);

    await waitFor(() => expect(screen.getByRole('option', { name: /300-N034/ })).toBeTruthy());
    fireEvent.change(document.getElementById('dealer-access-accounts')!, {
      target: { value: 'a1' },
    });
    fireEvent.click(screen.getByRole('option', { name: /300-N034/ }));
    fireEvent.click(screen.getByRole('button', { name: /add person/i }));

    const rows = [screen.getByTestId('person-row-0'), screen.getByTestId('person-row-1')];
    const values = [
      ['Person A', '+60120000001'],
      ['Person B', '+60120000002'],
    ];
    rows.forEach((row, i) => {
      fireEvent.change(within(row).getByLabelText('Name'), { target: { value: values[i][0] } });
      fireEvent.change(within(row).getByRole('textbox', { name: /person-phone/ }), {
        target: { value: values[i][1] },
      });
    });

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(
        within(screen.getByTestId('person-row-1')).getByText('This number belongs to a staff member.'),
      ).toBeTruthy(),
    );
    expect(within(screen.getByTestId('person-row-0')).queryByRole('alert')).toBeNull();
    expect((within(screen.getByTestId('person-row-0')).getByLabelText('Name') as HTMLInputElement).value).toBe(
      'Person A',
    );
    expect((within(screen.getByTestId('person-row-1')).getByLabelText('Name') as HTMLInputElement).value).toBe(
      'Person B',
    );
    expect(svc.grant).toHaveBeenCalledWith(
      expect.objectContaining({
        company: 'SRT',
        account_ids: ['a1'],
        people: [
          { name: 'Person A', phone: '+60120000001', role: 'employee' },
          { name: 'Person B', phone: '+60120000002', role: 'employee' },
        ],
      }),
    );
    // Shown under its row, so not also toasted.
    expect(toast.error).not.toHaveBeenCalled();
  });
});

describe('DealerAccessFormDialog - edit', () => {
  const person: DealerAccessRow = {
    contact_id: 'c1',
    name: 'Person C',
    phone: '+60 17-000 0003',
    company: 'SRT',
    company_name: 'Sorento',
    accounts: [{ ...ACCOUNTS[1], link_id: 'l1' }],
    access: 'owner',
    owner_tag: 'Sorento Business Owner',
    other_account: true,
  };

  it('keeps company and phone read-only and shows a refusal under the form', async () => {
    svc.updatePerson.mockRejectedValue(
      new Error('This person also has access through another account; ask the office to change their level.'),
    );
    render(<DealerAccessFormDialog open onOpenChange={vi.fn()} person={person} />);

    expect(screen.getByText('Sorento')).toBeTruthy();
    expect(screen.getByText('+60 17-000 0003')).toBeTruthy();
    expect(screen.queryByLabelText('Name')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(screen.getByText(/ask the office to change their level/)).toBeTruthy(),
    );
    expect(svc.updatePerson).toHaveBeenCalledWith('c1', {
      company: 'SRT',
      role: 'owner',
      account_ids: ['a2'],
    });
    // The form stays open.
    expect(screen.getByRole('button', { name: 'Save' })).toBeTruthy();
  });
});
