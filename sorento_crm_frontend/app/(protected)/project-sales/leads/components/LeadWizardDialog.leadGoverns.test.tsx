/**
 * LEAD-GOVERNS-REGISTER, Create lead wizard (UAC A1-A10). Red until the wizard is rebuilt:
 * steps Customer / The development / Who told us / Assign and confirm, a required server-search
 * Customer, no create row, no Firm, no "Buyer", and a submit-only salesperson with no Assign picker.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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

const createLead = vi.fn();
const assignLead = vi.fn();
const getUserLookup = vi.fn();
const listCustomerOptions = vi.fn();
const useCustomerSelectQuery = vi.fn(() => ({ data: [], isLoading: false }));

vi.mock('../../_shared/services/projectService', () => ({
  createLead: (...args: unknown[]) => createLead(...args),
  listCustomerOptions: (...args: unknown[]) => listCustomerOptions(...args),
  listParties: vi.fn(async () => ({
    data: [{ id: 'p1', name: 'Veritas Architects Sdn Bhd', party_type: 'architect' }],
    pagination: { total: 1, page: 1, limit: 200 },
  })),
  listLeads: vi.fn(),
  getLead: vi.fn(),
  updateLead: vi.fn(),
  changeLeadStatus: vi.fn(),
  previewQualify: vi.fn(),
  qualifyLead: vi.fn(),
  disqualifyLead: vi.fn(),
  reopenLead: vi.fn(),
  deleteLead: vi.fn(),
  listDisqualifyReasons: vi.fn(async () => []),
  getLeadMetrics: vi.fn(),
  getCustomerPortfolio: vi.fn(),
  listProjects: vi.fn(),
}));

vi.mock('../../_shared/services/leadAcceptanceService', () => ({
  listAwaitingAcceptance: vi.fn(),
  assignLead: (...args: unknown[]) => assignLead(...args),
  acceptLead: vi.fn(),
  declineLead: vi.fn(),
  nudgeLeadAssignee: vi.fn(),
}));

vi.mock('@/services/userSelectService', () => ({
  getUserLookup: (...args: unknown[]) => getUserLookup(...args),
}));

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// The old whole-list hook must not be what feeds the Customer picker (LGR-A3).
vi.mock('@/app/(protected)/order-management/shared/hooks/use-customer-select-query', () => ({
  useCustomerSelectQuery: () => useCustomerSelectQuery(),
}));

vi.mock('@/components/common/SearchableSelect', () => {
  type Opt = { value: string; label: string };
  function AsyncSelect({
    id,
    onChange,
    fetchOptions,
    emptyMessage,
    createOption,
  }: {
    id?: string;
    onChange: (next: string) => void;
    fetchOptions: (query: string, page: number) => Promise<Opt[]>;
    emptyMessage?: string;
    createOption?: { label: (q: string) => React.ReactNode; onCreate: (q: string) => void };
  }) {
    const [query, setQuery] = React.useState('');
    const [results, setResults] = React.useState<Opt[] | null>(null);
    return (
      <span>
        <input
          id={id}
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            void fetchOptions(event.target.value, 0).then(setResults);
          }}
        />
        {(results ?? []).map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => {
              onChange(option.value);
              setQuery(option.label);
              setResults(null);
            }}
          >
            {option.label}
          </button>
        ))}
        {results && results.length === 0 && query ? (
          <p data-testid="picker-empty">{emptyMessage ?? 'No results found.'}</p>
        ) : null}
        {createOption && query ? (
          <button type="button" onClick={() => createOption.onCreate(query)}>
            {createOption.label(query)}
          </button>
        ) : null}
      </span>
    );
  }
  return {
    SearchableSelect: (props: Record<string, unknown>) => {
      if (props.fetchOptions) return <AsyncSelect {...(props as never)} />;
      const { value, onChange, options, placeholder, id } = props as {
        value: string;
        onChange: (next: string) => void;
        options?: Opt[];
        placeholder?: string;
        id?: string;
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

vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { id: 'u-me', name: 'Sales A' } }, status: 'authenticated' }),
}));

let granted = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => granted.has(slug),
}));


import { LeadWizardDialog } from './LeadWizardDialog';

function renderWizard() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const onDone = vi.fn();
  render(
    <QueryClientProvider client={client}>
      <LeadWizardDialog onDone={onDone} />
    </QueryClientProvider>,
  );
  return { onDone };
}

const next = () => fireEvent.click(screen.getByRole('button', { name: /^Next$/ }));

async function pickCustomer(typed = 'KEDAI') {
  fireEvent.change(screen.getByLabelText(/^Customer/), { target: { value: typed } });
  fireEvent.click(await screen.findByRole('button', { name: 'KEDAI CONTOH SDN. BHD.' }));
}

async function toConfirm() {
  await pickCustomer();
  next();
  fireEvent.change(await screen.findByLabelText(/What is it/), {
    target: { value: 'TRX Zus Coffee fit-out' },
  });
  next();
  await screen.findByLabelText('Their reference');
  next();
}

beforeEach(() => {
  vi.clearAllMocks();
  granted = new Set(['projects.projects.edit']);
  listCustomerOptions.mockResolvedValue([{ value: 'c1', label: 'KEDAI CONTOH SDN. BHD.' }]);
  createLead.mockResolvedValue({ id: 'l1', lead_code: 'LEAD-000001', title: 'TRX Zus Coffee fit-out' });
  assignLead.mockResolvedValue({ id: 'l1', lead_code: 'LEAD-000001' });
  getUserLookup.mockResolvedValue([{ id: 'u-ali', name: 'Ali' }]);
});

describe('LGR-A1 / A2 steps and the required Customer', () => {
  it('A1 reads Customer, The development, Who told us, Assign and confirm in order', () => {
    renderWizard();
    const items = within(screen.getByRole('list', { name: 'Steps' })).getAllByRole('listitem');
    expect(items).toHaveLength(4);
    ['Customer', 'The development', 'Who told us', 'Assign and confirm'].forEach((label, i) =>
      expect(items[i]).toHaveTextContent(label),
    );
  });

  it('A2 step 1 is one required Customer picker; Next and Enter stay put until one is picked', async () => {
    renderWizard();
    expect(screen.getByLabelText(/^Customer/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/What is it/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Next$/ })).toBeDisabled();

    const form = screen.getByLabelText(/^Customer/).closest('form') as HTMLFormElement;
    fireEvent.submit(form);
    expect(screen.queryByLabelText(/What is it/)).not.toBeInTheDocument();

    await pickCustomer();
    expect(screen.getByRole('button', { name: /^Next$/ })).toBeEnabled();
  });
});

describe('LGR-A3 / A4 server search, name only, no create', () => {
  it('A3 searches the server with the typed text and never loads the whole customer list', async () => {
    renderWizard();
    fireEvent.change(screen.getByLabelText(/^Customer/), { target: { value: 'Zus' } });
    await waitFor(() => expect(listCustomerOptions).toHaveBeenCalledWith('Zus'));
    expect(useCustomerSelectQuery).not.toHaveBeenCalled();
    expect(await screen.findByRole('button', { name: 'KEDAI CONTOH SDN. BHD.' })).toBeInTheDocument();
  });

  it('A4 shows the empty message only: no Create row, no new-customer fields anywhere', async () => {
    listCustomerOptions.mockResolvedValue([]);
    renderWizard();
    fireEvent.change(screen.getByLabelText(/^Customer/), { target: { value: 'Gamuda' } });
    expect(await screen.findByTestId('picker-empty')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /create/i })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Phone/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Email/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Buyer name/)).not.toBeInTheDocument();
  });
});

describe('LGR-A6 development step', () => {
  it('A6 Rough value and Notes sit in The development, and there is no Lead detail step', async () => {
    renderWizard();
    await pickCustomer();
    next();
    expect(await screen.findByLabelText(/What is it/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Rough value/)).toBeInTheDocument();
    expect(screen.getByLabelText('Notes')).toBeInTheDocument();
    expect(screen.queryByText('Lead detail')).not.toBeInTheDocument();
  });
});

describe('LGR-A9 Who told us', () => {
  it('A9 holds Source, Their reference and Contact name only: no Firm picker', async () => {
    renderWizard();
    await pickCustomer();
    next();
    fireEvent.change(await screen.findByLabelText(/What is it/), { target: { value: 'TRX Zus Coffee fit-out' } });
    next();
    expect(await screen.findByLabelText('Select a source')).toBeInTheDocument();
    expect(screen.getByLabelText('Their reference')).toBeInTheDocument();
    expect(screen.getByLabelText('Contact name')).toBeInTheDocument();
    expect(screen.queryByLabelText('Search firms')).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^Firm/)).not.toBeInTheDocument();
  });
});

describe('LGR-A7 / A8 / A9 confirm and submit', () => {
  it('A7 Confirm lists Customer first with the picked name, no Firm, and the word Buyer nowhere', async () => {
    renderWizard();
    await toConfirm();
    const terms = Array.from(document.querySelectorAll('dt')).map((dt) => dt.textContent);
    expect(terms[0]).toBe('Customer');
    expect(within(document.querySelector('dl') as HTMLElement).getByText('KEDAI CONTOH SDN. BHD.')).toBeInTheDocument();
    expect(terms).not.toContain('Firm');
    expect(screen.queryByText(/buyer/i)).not.toBeInTheDocument();
  });

  it('A8 / A9 Create lead sends customer_id and never new_customer or informant_party_id', async () => {
    renderWizard();
    await toConfirm();
    fireEvent.click(await screen.findByRole('button', { name: 'Create lead' }));
    await waitFor(() => expect(createLead).toHaveBeenCalledTimes(1));
    const body = createLead.mock.calls[0][0] as Record<string, unknown>;
    expect(body.customer_id).toBe('c1');
    expect(body).not.toHaveProperty('new_customer');
    expect(body).not.toHaveProperty('informant_party_id');
  });
});

describe('LGR-A10 submit-only salesperson', () => {
  beforeEach(() => {
    granted = new Set(['projects.registrations.submit']);
  });

  it('has no Assign picker, shows themselves as Salesperson and makes no assign call', async () => {
    renderWizard();
    await toConfirm();
    expect(screen.queryByLabelText('Select a salesperson')).not.toBeInTheDocument();
    const facts = new Map(
      Array.from(document.querySelectorAll('dt')).map((dt) => [dt.textContent, dt.nextElementSibling?.textContent]),
    );
    expect(facts.get('Salesperson')).toBe('Sales A');

    fireEvent.click(await screen.findByRole('button', { name: 'Create lead' }));
    await waitFor(() => expect(createLead).toHaveBeenCalledTimes(1));
    expect(assignLead).not.toHaveBeenCalled();
  });

  it('an edit holder still gets the Assign picker', async () => {
    granted = new Set(['projects.projects.edit', 'projects.registrations.submit']);
    renderWizard();
    await toConfirm();
    expect(await screen.findByLabelText('Select a salesperson')).toBeInTheDocument();
  });
});

describe('LGR-D5 the lead handed back carries the assignee', () => {
  async function assignToAli() {
    const owner = await screen.findByLabelText('Select a salesperson');
    await waitFor(() => expect(screen.getByRole('option', { name: 'Ali' })).toBeInTheDocument());
    fireEvent.change(owner, { target: { value: 'u-ali' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create lead' }));
  }

  it('onDone receives the lead with owner_user_id of the person it was assigned to', async () => {
    assignLead.mockResolvedValue({ id: 'l1', lead_code: 'LEAD-000001', owner_user_id: 'u-ali' });
    const { onDone } = renderWizard();
    await toConfirm();
    await assignToAli();
    await waitFor(() => expect(assignLead).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(onDone).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'l1', owner_user_id: 'u-ali' }),
    );
  });

  it('when the assign call fails onDone gets the lead as created', async () => {
    assignLead.mockRejectedValue(new Error('Ali has left'));
    const { onDone } = renderWizard();
    await toConfirm();
    await assignToAli();
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    const lead = (onDone.mock.calls[0] as unknown as [Record<string, unknown>])[0];
    expect(lead.id).toBe('l1');
    expect(lead.owner_user_id).not.toBe('u-ali');
  });
});
