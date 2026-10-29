/**
 * LEAD-GOVERNS-REGISTER, lead edit dialog (UAC C1-C3): the picker says Customer, searches the
 * server like the wizard, is not clearable once the lead has a customer, there is no Firm picker,
 * and saving leaves an old lead's informant_party_id as it was.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { LeadWithAcceptance } from '../../../_shared/types/leadAcceptance.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const listCustomerOptions = vi.fn();
const useCustomerSelectQuery = vi.fn(() => ({ data: [], isLoading: false }));

vi.mock('../../../_shared/services/projectService', () => ({
  listCustomerOptions: (...args: unknown[]) => listCustomerOptions(...args),
  listParties: vi.fn(async () => ({
    data: [{ id: 'party-1', name: 'Veritas Architects Sdn Bhd', party_type: 'architect' }],
    pagination: { total: 1, page: 1, limit: 200 },
  })),
}));

vi.mock('@/app/(protected)/order-management/shared/hooks/use-customer-select-query', () => ({
  useCustomerSelectQuery: () => useCustomerSelectQuery(),
}));

vi.mock('@/components/common/SearchableSelect', () => {
  type Opt = { value: string; label: string };
  function AsyncSelect({
    id,
    value,
    onChange,
    onOptionChange,
    fetchOptions,
    selectedOption,
    clearable,
  }: {
    id?: string;
    value: string;
    onChange: (next: string) => void;
    onOptionChange?: (option: Opt | null) => void;
    fetchOptions: (query: string, page: number) => Promise<Opt[]>;
    selectedOption?: Opt;
    clearable?: boolean;
  }) {
    const [query, setQuery] = React.useState('');
    const [results, setResults] = React.useState<Opt[]>([]);
    const shown =
      query === '' && selectedOption && selectedOption.value === value ? selectedOption.label : query;
    return (
      <span>
        <input
          id={id}
          value={shown}
          data-clearable={String(Boolean(clearable))}
          onChange={(event) => {
            setQuery(event.target.value);
            void fetchOptions(event.target.value, 0).then(setResults);
          }}
        />
        {results.map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => {
              onChange(option.value);
              onOptionChange?.(option);
              setResults([]);
              setQuery('');
            }}
          >
            {option.label}
          </button>
        ))}
      </span>
    );
  }
  return {
    SearchableSelect: (props: Record<string, unknown>) => {
      if (props.fetchOptions) return <AsyncSelect {...(props as never)} />;
      const { id, value, onChange, options, placeholder } = props as {
        id?: string;
        value: string;
        onChange: (next: string) => void;
        options?: Opt[];
        placeholder?: string;
      };
      return (
        <select
          id={id}
          aria-label={placeholder ?? 'select'}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        >
          <option value="">{placeholder ?? ''}</option>
          {(options ?? []).map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      );
    },
  };
});

import { EditLeadInformantDialog } from './EditLeadInformantDialog';

function lead(over: Partial<LeadWithAcceptance> = {}): LeadWithAcceptance {
  return {
    id: 'l1',
    lead_code: 'LEAD-000001',
    title: 'TRX Zus Coffee fit-out',
    customer_id: 'c1',
    customer_name: 'KEDAI CONTOH SDN. BHD.',
    outcome: 'open',
    project_count: 0,
    possible_duplicates: [],
    can_edit: true,
    informant_source: 'bci',
    informant_ref: 'BCI-778812',
    informant_party_id: 'party-1',
    informant_party_label: 'Veritas Architects Sdn Bhd',
    informant_contact_name: 'Lim, QS',
    ...over,
  } as unknown as LeadWithAcceptance;
}

function renderDialog(row: LeadWithAcceptance = lead()) {
  const onConfirm = vi.fn(async () => {});
  const onDone = vi.fn();
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <EditLeadInformantDialog lead={row} onDone={onDone} onConfirm={onConfirm} />
    </QueryClientProvider>,
  );
  return { onConfirm, onDone };
}

beforeEach(() => {
  vi.clearAllMocks();
  listCustomerOptions.mockResolvedValue([
    { value: 'c2', label: 'WARUNG CONTOH ENTERPRISE' },
  ]);
});

describe('EditLeadInformantDialog (LEAD-GOVERNS-REGISTER)', () => {
  it('C1 labels the picker Customer, not Buyer', () => {
    renderDialog();
    expect(screen.getByLabelText(/^Customer/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Buyer/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Buyer$/)).not.toBeInTheDocument();
  });

  it('C1 titles the dialog "Who told us, and the customer" with no buyer word', () => {
    renderDialog();
    expect(screen.getByText('Who told us, and the customer')).toBeInTheDocument();
    expect(screen.queryByText(/buyer/i)).not.toBeInTheDocument();
  });

  it('C2 searches the server with the typed text instead of loading the whole list', async () => {
    renderDialog();
    fireEvent.change(screen.getByLabelText(/^Customer/), { target: { value: 'WARUNG' } });
    await waitFor(() => expect(listCustomerOptions).toHaveBeenCalledWith('WARUNG'));
    expect(useCustomerSelectQuery).not.toHaveBeenCalled();
  });

  it('C2 shows the lead\'s current customer and is not clearable once one is set', () => {
    renderDialog();
    const picker = screen.getByLabelText(/^Customer/);
    expect(picker).toHaveValue('KEDAI CONTOH SDN. BHD.');
    expect(picker).toHaveAttribute('data-clearable', 'false');
  });

  it('C3 has no Firm picker', () => {
    renderDialog();
    expect(screen.queryByLabelText('Search firms')).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^Firm/)).not.toBeInTheDocument();
  });

  it('C3 saving leaves an old lead\'s informant_party_id as it was', async () => {
    const { onConfirm } = renderDialog();
    fireEvent.change(screen.getByLabelText(/^Customer/), { target: { value: 'WARUNG' } });
    fireEvent.click(await screen.findByRole('button', { name: 'WARUNG CONTOH ENTERPRISE' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save informant' }));

    await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
    const body = (onConfirm.mock.calls[0] as unknown as [Record<string, unknown>])[0];
    expect(body.customer_id).toBe('c2');
    // Either left out of the body or sent back unchanged; never nulled.
    expect([undefined, 'party-1']).toContain(body.informant_party_id);
  });

  it('C3 a lead that never had a Firm does not gain one on save', async () => {
    const { onConfirm } = renderDialog(lead({ informant_party_id: null, informant_party_label: null }));
    fireEvent.click(screen.getByRole('button', { name: 'Save informant' }));
    await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
    const body = (onConfirm.mock.calls[0] as unknown as [Record<string, unknown>])[0];
    expect([undefined, null]).toContain(body.informant_party_id);
  });
});
