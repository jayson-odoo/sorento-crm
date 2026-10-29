/**
 * P1 - LeadWizardDialog (AC-A1, AC-A2, AC-A3, AC-A4).
 *
 * Three things carry the design and are pinned here:
 * - the customer is the one required decision (LEAD-GOVERNS-REGISTER A2), then the development
 * - the informant is collected as its own thing and posted as informant_* fields
 * - picking a salesperson calls ASSIGN after the create, because assignment stamps the
 *     clock and notifies them; it is not a column on the create
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

async function walkToConfirm() {
  await pickCustomer();
  next();
  fireEvent.change(await screen.findByLabelText(/What is it/), {
    target: { value: 'Tower behind the showroom' },
  });
  next();
  await screen.findByLabelText('Their reference');
  next();
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

describe('LeadWizardDialog', () => {
  it('opens on the customer, which gates Next, then asks for the development', async () => {
    renderWizard();

    expect(screen.getByLabelText(/^Customer/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/What is it/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Next$/ })).toBeDisabled();

    await pickCustomer();
    expect(screen.getByRole('button', { name: /^Next$/ })).toBeEnabled();
    next();

    expect(await screen.findByLabelText(/What is it/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Next$/ })).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/What is it/), {
      target: { value: 'Tower behind the showroom' },
    });
    expect(screen.getByRole('button', { name: /^Next$/ })).toBeEnabled();
  });

  it('collects the informant separately from the customer', async () => {
    renderWizard();
    await pickCustomer();
    next();
    fireEvent.change(await screen.findByLabelText(/What is it/), {
      target: { value: 'Tower behind the showroom' },
    });
    next();

    expect(await screen.findByLabelText('Their reference')).toBeInTheDocument();
    // The stepper names the step; the fieldset does not print it a second time.
    expect(screen.getAllByText('Who told us')).toHaveLength(2); // sr-only circle + label

    expect(screen.getByLabelText('Contact name')).toBeInTheDocument();
    // The customer is nowhere near this step.
    expect(screen.queryByLabelText(/^Customer/)).not.toBeInTheDocument();
  });

  it('records a lead with a customer and an informant', async () => {
    const { onDone } = renderWizard();

    await pickCustomer();
    next();
    fireEvent.change(await screen.findByLabelText(/What is it/), {
      target: { value: 'Tower behind the showroom' },
    });
    fireEvent.change(screen.getByLabelText('Location'), {
      target: { value: 'Setia Alam' },
    });
    next();

    fireEvent.change(await screen.findByLabelText('Select a source'), {
      target: { value: 'bci' },
    });
    fireEvent.change(screen.getByLabelText('Their reference'), {
      target: { value: 'BCI-778812' },
    });
    fireEvent.change(screen.getByLabelText('Contact name'), {
      target: { value: 'Lim, QS' },
    });
    next();

    fireEvent.click(await screen.findByRole('button', { name: 'Create lead' }));

    await waitFor(() => expect(createLead).toHaveBeenCalledTimes(1));
    expect(createLead).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Tower behind the showroom',
        customer_id: 'c1',
        informant_source: 'bci',
        informant_ref: 'BCI-778812',
        informant_contact_name: 'Lim, QS',
      }),
    );
    expect(assignLead).not.toHaveBeenCalled();
    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  it('assigns after creating when a salesperson is picked', async () => {
    renderWizard();

    await walkToConfirm();

    const owner = await screen.findByLabelText('Select a salesperson');
    await waitFor(() => expect(getUserLookup).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.getByRole('option', { name: 'Ali' })).toBeInTheDocument(),
    );
    fireEvent.change(owner, { target: { value: 'u-ali' } });

    fireEvent.click(screen.getByRole('button', { name: 'Create lead' }));

    await waitFor(() => expect(assignLead).toHaveBeenCalledTimes(1));
    expect(assignLead).toHaveBeenCalledWith('l1', {
      owner_user_id: 'u-ali',
      note: null,
    });
  });

  it('keeps the lead when the assignment fails, rather than losing the whole entry', async () => {
    assignLead.mockRejectedValue(new Error('Ali has left'));
    const { onDone } = renderWizard();

    await walkToConfirm();

    const owner = await screen.findByLabelText('Select a salesperson');
    await waitFor(() =>
      expect(screen.getByRole('option', { name: 'Ali' })).toBeInTheDocument(),
    );
    fireEvent.change(owner, { target: { value: 'u-ali' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create lead' }));

    await waitFor(() => expect(createLead).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  it('summarises who told us and the customer on the last step', async () => {
    renderWizard();

    await pickCustomer();
    next();
    fireEvent.change(await screen.findByLabelText(/What is it/), {
      target: { value: 'Tower behind the showroom' },
    });
    next();
    fireEvent.change(await screen.findByLabelText('Select a source'), {
      target: { value: 'referral' },
    });
    next();

    expect(await screen.findByText('KEDAI CONTOH SDN. BHD.')).toBeInTheDocument();
    expect(screen.getByText('Referral')).toBeInTheDocument();
  });

  it('is titled Create lead and carries no explanatory prose (owner, 13 Oct)', () => {
    renderWizard();
    expect(screen.getByRole('heading', { name: 'Create lead' })).toBeInTheDocument();
    expect(screen.queryByText(/A lead claims nothing/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Vague is fine/)).not.toBeInTheDocument();
  });

  it('shows progress as a numbered stepper, not a row of badges', () => {
    renderWizard();
    const steps = screen.getByRole('list', { name: 'Steps' });
    expect(steps).toBeInTheDocument();
    expect(within(steps).getAllByRole('listitem')).toHaveLength(4);
    expect(
      within(steps).getByText('Customer').closest('[aria-current="step"]'),
    ).not.toBeNull();
  });

  it('offers no way to create a customer from the dropdown (LGR-A4)', async () => {
    renderWizard();
    fireEvent.change(screen.getByLabelText(/^Customer/), { target: { value: 'Gamuda Builders' } });

    expect(screen.queryByRole('button', { name: /^Create/ })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Buyer name/)).not.toBeInTheDocument();
  });

  it('lists who told us as separate labelled fields, never a dot-joined line', async () => {
    renderWizard();
    await pickCustomer();
    next();
    fireEvent.change(await screen.findByLabelText(/What is it/), {
      target: { value: 'Tower behind the showroom' },
    });
    next();
    fireEvent.change(await screen.findByLabelText('Select a source'), {
      target: { value: 'referral' },
    });
    fireEvent.change(screen.getByLabelText('Contact name'), {
      target: { value: 'Lim' },
    });
    next();

    await screen.findByText('Referral');
    expect(screen.getByText('Source')).toBeInTheDocument();
    expect(screen.getByText('Contact')).toBeInTheDocument();
    expect(screen.getByText('Lim')).toBeInTheDocument();
    expect(screen.queryByText(/ · /)).not.toBeInTheDocument();
    expect(screen.queryByText(/They accept or decline it/)).not.toBeInTheDocument();
  });

  it('starts from a title handed in by the caller and reports the created lead', async () => {
    const client = new QueryClient();
    const onDone = vi.fn();
    render(
      <QueryClientProvider client={client}>
        <LeadWizardDialog onDone={onDone} initialTitle="Setia Alam Phase 3B" />
      </QueryClientProvider>,
    );
    await pickCustomer();
    next();
    expect(await screen.findByLabelText(/What is it/)).toHaveValue('Setia Alam Phase 3B');
    next();
    next();
    fireEvent.click(await screen.findByRole('button', { name: 'Create lead' }));
    await waitFor(() =>
      expect(onDone).toHaveBeenCalledWith(expect.objectContaining({ id: 'l1' })),
    );
  });

  it('does not let its submit bubble to a form it is opened from', async () => {
    const outerSubmit = vi.fn((event: React.FormEvent) => event.preventDefault());
    const client = new QueryClient();
    render(
      <QueryClientProvider client={client}>
        <form onSubmit={outerSubmit}>
          <LeadWizardDialog onDone={vi.fn()} initialTitle="Tower" />
        </form>
      </QueryClientProvider>,
    );
    await pickCustomer();
    next();
    await screen.findByLabelText(/What is it/);
    next();
    expect(outerSubmit).not.toHaveBeenCalled();
  });
});
