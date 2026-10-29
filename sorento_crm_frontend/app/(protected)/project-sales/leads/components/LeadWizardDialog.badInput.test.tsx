/** NUMBER-FIELDS round 3 (R6): bad input in Rough value is refused with the sentence, nothing is sent. */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
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

vi.mock('../../_shared/services/projectService', () => ({
  createLead: (...args: unknown[]) => createLead(...args),
  listParties: vi.fn(async () => ({
    data: [
      { id: 'p1', name: 'Veritas Architects Sdn Bhd', party_type: 'architect' },
      { id: 'p2', name: 'Setia Land', party_type: 'developer' },
    ],
    pagination: { total: 2, page: 1, limit: 200 },
  })),
  listLeads: vi.fn(),
  listCustomerOptions: vi.fn(async () => [
    { value: 'c1', label: 'KEDAI CONTOH SDN. BHD.' },
  ]),
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

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
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

async function pickCustomer() {
  fireEvent.change(screen.getByLabelText(/^Customer/), { target: { value: 'KEDAI' } });
  fireEvent.click(await screen.findByRole('button', { name: 'KEDAI CONTOH SDN. BHD.' }));
}

function next() {
  fireEvent.click(screen.getByRole('button', { name: /^Next$/ }));
}

beforeEach(() => {
  vi.clearAllMocks();
  createLead.mockResolvedValue({ id: 'l1', lead_code: 'LEAD-000001', title: 'Tower' });
  assignLead.mockResolvedValue({
    id: 'l1',
    lead_code: 'LEAD-000001',
    owner_name: 'Ali',
  });
  getUserLookup.mockResolvedValue([{ id: 'u-ali', name: 'Ali' }]);
});

import { typeBadInput } from '@/test-utils/badInput';

describe('LeadWizardDialog bad number input (R6)', () => {
  it('Rough value with bad input: the lead is not created and the sentence shows under the box', async () => {
    renderWizard();
    await pickCustomer();
    next();
    fireEvent.change(await screen.findByLabelText(/What is it/), {
      target: { value: 'Tower behind the showroom' },
    });
    typeBadInput(await screen.findByLabelText(/Rough value/));
    // Walk to the end; a screen that stops the walk (or sends it back here) is as good.
    for (let i = 0; i < 3; i += 1) {
      const create = screen.queryByRole('button', { name: 'Create lead' });
      if (create) {
        fireEvent.click(create);
        break;
      }
      const nextButton = screen.queryByRole('button', { name: /^Next$/ });
      if (!nextButton) break;
      fireEvent.click(nextButton);
      await screen.findAllByRole("button", { name: /^Back$|^Next$|Create lead/ });
    }
    expect(
      await screen.findByText('Enter a number of at least 0, or leave it blank.'),
    ).toBeInTheDocument();
    expect(createLead).not.toHaveBeenCalled();
  });

  it('S4: no sentence while typing, Next stays enabled, a refused press shows it and stays, a valid value clears it', async () => {
    renderWizard();
    await pickCustomer();
    next();
    fireEvent.change(await screen.findByLabelText(/What is it/), {
      target: { value: 'Tower behind the showroom' },
    });
    const box = await screen.findByLabelText(/Rough value/);
    typeBadInput(box);
    // Typing alone says nothing and does not lock the button (owner Q1 / Q4).
    expect(screen.queryByText(/Enter a number/)).not.toBeInTheDocument();
    const nextButton = screen.getByRole('button', { name: /^Next$/ });
    expect(nextButton).not.toBeDisabled();
    // The press is refused: the sentence shows and the walk does not advance.
    fireEvent.click(nextButton);
    expect(await screen.findByText(/Enter a number/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Rough value/)).toBeInTheDocument();
    // From then on it is live: a valid value clears it.
    fireEvent.change(screen.getByLabelText(/Rough value/), { target: { value: '1500.50' } });
    expect(screen.queryByText(/Enter a number/)).not.toBeInTheDocument();
  });
});
