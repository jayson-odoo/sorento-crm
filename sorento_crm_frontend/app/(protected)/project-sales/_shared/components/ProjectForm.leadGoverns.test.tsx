/**
 * LEAD-GOVERNS-REGISTER, the Register a project form (UAC D1-D8). Red until the form is rebuilt:
 * a "Lead, customer and salesperson" section, Lead required on Register, Customer a read-only value
 * filled from the lead (a search picker only when the lead has none), AI extract never sets it.
 *
 * Seams: leads come from listLeads (rows carry customer_id, customer_name, owner_user_id) and
 * getLead; permissions from useHasPermission, the same hook ProjectForm uses for submitOnly.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Project } from '../types/project.types';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  usePathname: () => '/project-sales/new',
  useRouter: () => ({ push, replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
}));

let sessionUser: { id: string; name: string } | null = { id: 'u-me', name: 'Me' };
vi.mock('next-auth/react', () => ({
  useSession: () =>
    sessionUser
      ? { data: { user: sessionUser }, status: 'authenticated' }
      : { data: null, status: 'unauthenticated' },
}));

let granted = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => granted.has(slug),
}));

const getUserLookup = vi.fn();
vi.mock('@/services/userSelectService', () => ({
  getUserLookup: (...args: unknown[]) => getUserLookup(...args),
}));

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), custom: vi.fn() },
}));

const listParties = vi.fn();
const listProjectTypes = vi.fn();
const listProjectTemplates = vi.fn();
const previewClashes = vi.fn();
const registerProject = vi.fn();
const updateProject = vi.fn();
const listLeads = vi.fn();
const getLead = vi.fn();
const listCustomerOptions = vi.fn();

// Same absolute module `../hooks/useProjects.ts` imports as `../services/projectService`
// (both files sit one level under `_shared/`), so this mock reaches every hook ProjectForm
// will use without ProjectForm having to know the service is mocked.
vi.mock('../services/projectService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/projectService')>();
  return {
    ...actual,
    listParties: (...args: unknown[]) => listParties(...args),
    listProjectTypes: (...args: unknown[]) => listProjectTypes(...args),
    listProjectTemplates: (...args: unknown[]) => listProjectTemplates(...args),
    previewClashes: (...args: unknown[]) => previewClashes(...args),
    registerProject: (...args: unknown[]) => registerProject(...args),
    updateProject: (...args: unknown[]) => updateProject(...args),
    listLeads: (...args: unknown[]) => listLeads(...args),
    getLead: (...args: unknown[]) => getLead(...args),
    listCustomerOptions: (...args: unknown[]) => listCustomerOptions(...args),
  };
});

type Option = { value: string; label: string };

vi.mock('@/components/common/SearchableSelect', () => {
  function StaticSelect({
    id,
    value,
    onChange,
    onOptionChange,
    options,
    disabled,
    clearable,
  }: {
    id?: string;
    value: string;
    onChange: (next: string) => void;
    onOptionChange?: (option: Option | null) => void;
    options?: Option[];
    disabled?: boolean;
    clearable?: boolean;
  }) {
    return (
      <span>
        <select
          id={id}
          value={value}
          disabled={disabled}
          onChange={(event) => {
            const next = event.target.value;
            onChange(next);
            onOptionChange?.((options ?? []).find((option) => option.value === next) ?? null);
          }}
        >
          <option value="" />
          {(options ?? []).map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        {clearable && value && (
          <button
            type="button"
            onClick={() => {
              onChange('');
              onOptionChange?.(null);
            }}
          >
            Clear
          </button>
        )}
      </span>
    );
  }

  // Async mode: the Lead field. Fetches on every keystroke (no debounce, this is a test
  // double) and shows the caller-supplied `selectedOption` when nothing has been typed.
  function AsyncSelect({
    id,
    value,
    onChange,
    onOptionChange,
    fetchOptions,
    selectedOption,
    clearable,
    createOption,
  }: {
    id?: string;
    value: string;
    onChange: (next: string) => void;
    onOptionChange?: (option: Option | null) => void;
    fetchOptions?: (query: string, pageIndex: number) => Promise<Option[]>;
    selectedOption?: Option;
    clearable?: boolean;
    createOption?: { label: (q: string) => React.ReactNode; onCreate: (q: string) => void };
  }) {
    const [query, setQuery] = React.useState('');
    const [results, setResults] = React.useState<Option[]>([]);
    const displayValue =
      query === '' && selectedOption && selectedOption.value === value
        ? selectedOption.label
        : query;
    return (
      <span>
        <input
          id={id}
          value={displayValue}
          onChange={(event) => {
            setQuery(event.target.value);
            void fetchOptions?.(event.target.value, 0).then(setResults);
          }}
          placeholder="Search"
        />
        <div>
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
          {createOption && query ? (
            <button type="button" onClick={() => createOption.onCreate(query)}>
              {createOption.label(query)}
            </button>
          ) : null}
        </div>
        {clearable && value && (
          <button
            type="button"
            aria-label={id === 'project-lead' ? 'Clear lead' : `Clear ${id}`}
            onClick={() => {
              onChange('');
              onOptionChange?.(null);
              setQuery('');
            }}
          >
            Clear
          </button>
        )}
      </span>
    );
  }

  return {
    SearchableSelect: (props: Record<string, unknown>) =>
      props.fetchOptions ? (
        <AsyncSelect {...(props as never)} />
      ) : (
        <StaticSelect {...(props as never)} />
      ),
  };
});

vi.mock('@/components/ui/date-range-picker', () => ({
  DateRangePicker: ({
    id,
    from,
    to,
    onChange,
  }: {
    id?: string;
    from: string | null;
    to: string | null;
    onChange: (next: { from: string | null; to: string | null }) => void;
  }) => (
    <input
      id={id}
      value={[from ?? '', to ?? ''].join(',')}
      onChange={(event) => {
        const [nextFrom, nextTo] = event.target.value.split(',');
        onChange({ from: nextFrom || null, to: nextTo || null });
      }}
    />
  ),
}));


vi.mock('./ProjectAIExtractDialog', () => ({
  ProjectAIExtractDialog: ({ onFill }: { onFill: (fill: Record<string, unknown>) => void }) => (
    <button
      type="button"
      onClick={() =>
        onFill({
          title: 'Tajuk Dari Gambar CONTOH',
          state: 'Selangor',
          mukim: 'Batu',
          customer: { id: 'c-9', name: 'WARUNG CONTOH ENTERPRISE' },
        })
      }
    >
      Apply extract
    </button>
  ),
}));

vi.mock('../../leads/components/LeadWizardDialog', () => ({
  LeadWizardDialog: ({
    initialTitle,
    onDone,
  }: {
    initialTitle?: string;
    onDone: (lead?: Record<string, unknown>) => void;
  }) => (
    <div role="dialog" aria-label="Create lead">
      <span>wizard title: {initialTitle}</span>
      <button
        type="button"
        onClick={() =>
          onDone({
            id: 'lead-new',
            lead_code: 'LEAD-000077',
            title: initialTitle ?? '',
            customer_id: 'c-1',
            customer_name: 'KEDAI CONTOH SDN. BHD.',
            owner_user_id: 'u-me',
          })
        }
      >
        Finish wizard
      </button>
    </div>
  ),
}));

import { ProjectForm } from './ProjectForm';

const LEAD_A = {
  id: 'lead-1',
  lead_code: 'LEAD-000001',
  title: 'TRX Zus Coffee fit-out',
  outcome: 'open',
  customer_id: 'c-1',
  customer_name: 'KEDAI CONTOH SDN. BHD.',
  owner_user_id: 'u-2',
  owner_name: 'Sales B',
  project_count: 0,
  possible_duplicates: [],
  can_edit: true,
};
const LEAD_NO_CUSTOMER = {
  ...LEAD_A,
  id: 'lead-2',
  lead_code: 'LEAD-000002',
  title: 'Menara Tanpa Pelanggan',
  customer_id: null,
  customer_name: null,
  owner_user_id: null,
  owner_name: null,
};
const LEAD_B = {
  ...LEAD_A,
  id: 'lead-3',
  lead_code: 'LEAD-000003',
  title: 'Gerai Contoh Phase 2',
  customer_id: 'c-2',
  customer_name: 'WARUNG CONTOH ENTERPRISE',
  owner_user_id: 'u-me',
  owner_name: 'Sales A',
};
const ALL_LEADS = [LEAD_A, LEAD_NO_CUSTOMER, LEAD_B];

function baseProject(over: Record<string, unknown> = {}): Project {
  return {
    id: 'p1',
    project_code: 'PRJ-000001',
    title: 'Setia Alam Phase 3B',
    outcome: 'open',
    is_critical: false,
    developer_party_id: null,
    developer_name: null,
    type_id: null,
    template_id: null,
    owner_user_id: 'u-me',
    owner_name: 'Sales A',
    lead_id: 'lead-1',
    lead_code: 'LEAD-000001',
    lead_title: 'TRX Zus Coffee fit-out',
    customer_id: 'c-1',
    customer_name: 'KEDAI CONTOH SDN. BHD.',
    next_action_overdue: false,
    stale_level: 0,
    is_unattended: false,
    open_task_count: 0,
    can_edit: true,
    ...over,
  } as unknown as Project;
}

function renderForm(props: { mode: 'create' } | { mode: 'edit'; project: Project }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ProjectForm {...props} />
    </QueryClientProvider>,
  );
}

const section = () =>
  screen
    .getByRole('button', { name: /Lead, customer and salesperson/ })
    .closest('[data-slot="card"]') as HTMLElement;
const typeTitle = (text: string) =>
  fireEvent.change(screen.getByLabelText(/project title/i), { target: { value: text } });
async function pickLead(typed: string, name: string) {
  fireEvent.change(screen.getByLabelText(/^Lead/), { target: { value: typed } });
  fireEvent.click(await screen.findByRole('button', { name }));
}
const registerButton = () => screen.getByRole('button', { name: 'Register project' });
const customerTextbox = () => screen.queryByRole('textbox', { name: /^Customer/ });

beforeEach(() => {
  vi.clearAllMocks();
  sessionUser = { id: 'u-me', name: 'Sales A' };
  granted = new Set(['projects.projects.edit', 'projects.projects.manage']);
  listParties.mockResolvedValue({ data: [], pagination: { total: 0, page: 1, limit: 20 } });
  listProjectTypes.mockResolvedValue([]);
  listProjectTemplates.mockResolvedValue([]);
  previewClashes.mockResolvedValue({ candidates: [], would_block: false });
  registerProject.mockResolvedValue({ id: 'new1', project_code: 'PRJ-000099' });
  updateProject.mockResolvedValue(baseProject());
  listLeads.mockImplementation(async (params: { query?: string }) => {
    const q = (params.query ?? '').toLowerCase();
    const data = ALL_LEADS.filter((lead) => !q || lead.title.toLowerCase().includes(q));
    return { data, pagination: { total: data.length, page: 1, limit: 20 } };
  });
  getLead.mockImplementation(async (id: string) => [...ALL_LEADS, {
    ...LEAD_A, id: 'lead-new', lead_code: 'LEAD-000077', title: 'Tower Q',
  }].find((lead) => lead.id === id));
  getUserLookup.mockResolvedValue([
    { id: 'u-me', name: 'Sales A' },
    { id: 'u-2', name: 'Sales B' },
  ]);
  listCustomerOptions.mockResolvedValue([{ value: 'c-1', label: 'KEDAI CONTOH SDN. BHD.' }]);
});

describe('LGR-D1 the Lead, customer and salesperson section', () => {
  it('names the bottom section and drops the old one', () => {
    renderForm({ mode: 'create' });
    expect(screen.getByRole('button', { name: /Lead, customer and salesperson/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Salesperson and customer/ })).toBeNull();
  });

  it('holds Lead, Customer, Salesperson in that order, and Details holds no Lead', () => {
    renderForm({ mode: 'create' });
    fireEvent.click(screen.getByRole('button', { name: /^Details/ }));
    const details = screen.getByRole('button', { name: /^Details/ }).closest('[data-slot="card"]') as HTMLElement;
    expect(within(details).queryByLabelText(/^Lead/)).toBeNull();

    const box = section();
    const lead = within(box).getByLabelText(/^Lead/);
    const customer = within(box).getAllByText(/^Customer/)[0];
    const salesperson = within(box).getByLabelText('Salesperson');
    const follows = (a: Element, b: Element) =>
      Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
    expect(follows(lead, customer)).toBe(true);
    expect(follows(customer, salesperson)).toBe(true);
  });
});

describe('LGR-D2 Customer is read-only, filled from the lead', () => {
  it('shows the lead\'s customer name once a lead is picked, with no editable Customer', async () => {
    renderForm({ mode: 'create' });
    expect(customerTextbox()).toBeNull();
    await pickLead('TRX', 'TRX Zus Coffee fit-out');
    expect(await within(section()).findByText('KEDAI CONTOH SDN. BHD.')).toBeInTheDocument();
    expect(customerTextbox()).toBeNull();
  });

  it('clearing the lead clears the customer', async () => {
    renderForm({ mode: 'create' });
    await pickLead('TRX', 'TRX Zus Coffee fit-out');
    await within(section()).findByText('KEDAI CONTOH SDN. BHD.');
    fireEvent.click(screen.getByRole('button', { name: 'Clear lead' }));
    await waitFor(() =>
      expect(within(section()).queryByText('KEDAI CONTOH SDN. BHD.')).toBeNull(),
    );
  });

  it('Register stays disabled until a lead is picked, then sends lead_id', async () => {
    renderForm({ mode: 'create' });
    typeTitle('TRX Zus Coffee fit-out');
    expect(registerButton()).toBeDisabled();
    await pickLead('TRX', 'TRX Zus Coffee fit-out');
    await waitFor(() => expect(registerButton()).toBeEnabled());
    fireEvent.click(registerButton());
    await waitFor(() => expect(registerProject).toHaveBeenCalledTimes(1));
    expect(registerProject).toHaveBeenCalledWith(expect.objectContaining({ lead_id: 'lead-1' }));
  });
});

describe('LGR-D3 a lead with no customer asks for one', () => {
  it('turns Customer into the required search picker and holds Register until one is picked', async () => {
    renderForm({ mode: 'create' });
    typeTitle('Menara Tanpa Pelanggan');
    await pickLead('Tanpa', 'Menara Tanpa Pelanggan');

    const picker = await screen.findByLabelText(/^Customer/);
    expect(registerButton()).toBeDisabled();
    fireEvent.change(picker, { target: { value: 'KEDAI' } });
    await waitFor(() => expect(listCustomerOptions).toHaveBeenCalledWith('KEDAI'));
    fireEvent.click(await screen.findByRole('button', { name: 'KEDAI CONTOH SDN. BHD.' }));
    await waitFor(() => expect(registerButton()).toBeEnabled());
    fireEvent.click(registerButton());
    await waitFor(() => expect(registerProject).toHaveBeenCalledTimes(1));
    expect(registerProject).toHaveBeenCalledWith(
      expect.objectContaining({ lead_id: 'lead-2', customer_id: 'c-1' }),
    );
  });
});

describe('LGR-D4 Salesperson follows the lead', () => {
  const salesperson = () => screen.getByLabelText('Salesperson') as HTMLSelectElement;

  it('a user who may change the salesperson gets the lead\'s assignee', async () => {
    renderForm({ mode: 'create' });
    await waitFor(() => expect(salesperson().value).toBe('u-me'));
    await pickLead('TRX', 'TRX Zus Coffee fit-out');
    await waitFor(() => expect(salesperson().value).toBe('u-2'));
  });

  it('a lead with no assignee leaves Salesperson as it was', async () => {
    renderForm({ mode: 'create' });
    await waitFor(() => expect(salesperson().value).toBe('u-me'));
    await pickLead('Tanpa', 'Menara Tanpa Pelanggan');
    await screen.findByLabelText(/^Customer/);
    expect(salesperson().value).toBe('u-me');
  });

  it('a user who may not change it stays the signed-in user', async () => {
    granted = new Set(['projects.projects.edit']);
    renderForm({ mode: 'create' });
    await waitFor(() => expect(salesperson().value).toBe('u-me'));
    await pickLead('TRX', 'TRX Zus Coffee fit-out');
    await within(section()).findByText('KEDAI CONTOH SDN. BHD.');
    expect(salesperson().value).toBe('u-me');
  });
});

describe('LGR-D5 Create lead from the picker', () => {
  it('opens the wizard with the typed text, then picks the new lead and shows its customer', async () => {
    renderForm({ mode: 'create' });
    typeTitle('Tower Q');
    fireEvent.change(screen.getByLabelText(/^Lead/), { target: { value: 'Tower Q' } });
    fireEvent.click(await screen.findByRole('button', { name: /Create lead .Tower Q./ }));
    const wizard = await screen.findByRole('dialog', { name: 'Create lead' });
    expect(within(wizard).getByText('wizard title: Tower Q')).toBeInTheDocument();
    fireEvent.click(within(wizard).getByRole('button', { name: 'Finish wizard' }));

    expect(await within(section()).findByText('KEDAI CONTOH SDN. BHD.')).toBeInTheDocument();
    await waitFor(() => expect(registerButton()).toBeEnabled());
    fireEvent.click(registerButton());
    await waitFor(() =>
      expect(registerProject).toHaveBeenCalledWith(expect.objectContaining({ lead_id: 'lead-new' })),
    );
  });
});

describe('LGR-D6 AI extract never sets Customer', () => {
  it('fills the title and mukim but leaves Customer empty and Register disabled', async () => {
    renderForm({ mode: 'create' });
    fireEvent.click(screen.getByRole('button', { name: 'Apply extract' }));
    await waitFor(() =>
      expect((screen.getByLabelText(/project title/i) as HTMLTextAreaElement).value).toBe(
        'Tajuk Dari Gambar CONTOH',
      ),
    );
    expect(screen.queryByText('WARUNG CONTOH ENTERPRISE')).toBeNull();
    expect(registerButton()).toBeDisabled();
  });
});

describe('LGR-D7 edit mode', () => {
  it('with a lead, Customer is the read-only project customer and Lead is optional', () => {
    renderForm({ mode: 'edit', project: baseProject() });
    expect(within(section()).getByText('KEDAI CONTOH SDN. BHD.')).toBeInTheDocument();
    expect(customerTextbox()).toBeNull();
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeEnabled();
  });

  it('picking a different lead re-fills Customer from that lead', async () => {
    renderForm({ mode: 'edit', project: baseProject() });
    await pickLead('Gerai', 'Gerai Contoh Phase 2');
    expect(await within(section()).findByText('WARUNG CONTOH ENTERPRISE')).toBeInTheDocument();
    expect(within(section()).queryByText('KEDAI CONTOH SDN. BHD.')).toBeNull();
  });

  it('with no lead, Customer is the editable picker and Save changes is enabled', () => {
    renderForm({
      mode: 'edit',
      project: baseProject({ lead_id: null, lead_code: null, lead_title: null }),
    });
    expect(screen.getByLabelText(/^Customer/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeEnabled();
  });
});

describe('LGR-D8 submit-only salesperson', () => {
  beforeEach(() => {
    granted = new Set(['projects.registrations.submit']);
  });

  it('sees the same section with a Lead picker; Save draft needs no lead, Submit does', async () => {
    renderForm({ mode: 'create' });
    expect(screen.getByRole('button', { name: /Lead, customer and salesperson/ })).toBeInTheDocument();
    expect(screen.getByLabelText(/^Lead/)).toBeInTheDocument();
    typeTitle('TRX Zus Coffee fit-out');
    expect(screen.getByRole('button', { name: 'Save draft' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Submit for approval' })).toBeDisabled();

    await pickLead('TRX', 'TRX Zus Coffee fit-out');
    await waitFor(() => expect(screen.getByRole('button', { name: 'Submit for approval' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Submit for approval' }));
    await waitFor(() => expect(registerProject).toHaveBeenCalledTimes(1));
    expect(registerProject).toHaveBeenCalledWith(
      expect.objectContaining({ lead_id: 'lead-1', submit: true }),
    );
  });

  it('keeps Salesperson as the signed-in user when a lead assigned to someone else is picked', async () => {
    renderForm({ mode: 'create' });
    await pickLead('TRX', 'TRX Zus Coffee fit-out');
    await within(section()).findByText('KEDAI CONTOH SDN. BHD.');
    expect((screen.getByLabelText('Salesperson') as HTMLSelectElement).value).toBe('u-me');
  });
});
