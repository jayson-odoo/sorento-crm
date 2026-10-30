/**
 * PS-REGISTER-CHECK-FIRST section L (owner ruling 30 Oct): registration has no lead. Replaces
 * ProjectForm.leadGoverns.test.tsx (LEAD-GOVERNS-REGISTER), whose every case pinned the Lead picker,
 * the read-only customer-from-lead, or lead_id on the body.
 * AC-L1 no Lead field / no "Create lead", section "Customer and salesperson", Customer is the
 * always-editable search picker (listCustomerOptions), required for Register / Submit, optional for
 * Save draft; the register body carries customer_id and NO lead_id key. AC-L5 edit keeps the lead
 * link untouched (no lead_id on the PUT).
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
      <button
        type="button"
        onClick={() =>
          onDone({
            id: 'lead-new',
            lead_code: 'LEAD-000077',
            title: initialTitle ?? '',
            customer_id: 'c-1',
            customer_name: 'KEDAI CONTOH SDN. BHD.',
            owner_user_id: 'u-2',
          })
        }
      >
        Finish wizard assigned to Sales B
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
    .getByRole('button', { name: /^Customer and salesperson/ })
    .closest('[data-slot="card"]') as HTMLElement;
const typeTitle = (text: string) =>
  fireEvent.change(screen.getByLabelText(/project title/i), { target: { value: text } });
async function pickCustomer(typed = 'KEDAI', name = 'KEDAI CONTOH SDN. BHD.') {
  fireEvent.change(screen.getByLabelText(/^Customer/), { target: { value: typed } });
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

/**
 * PS-REGISTER-CHECK-FIRST: create mode opens on the Check step; walk it to Details.
 * Types the title if the field is empty, Checks, waits for the result, presses Next.
 */
async function toDetails(text = 'Setia Alam Phase 3B') {
  const box = screen.getByLabelText(/project title/i) as HTMLTextAreaElement;
  if (!box.value) fireEvent.change(box, { target: { value: text } });
  fireEvent.click(screen.getByRole('button', { name: 'Check' }));
  await screen.findByText('No clash');
  fireEvent.click(screen.getByRole('button', { name: 'Next' }));
  await screen.findByRole('button', { name: /^Customer and salesperson/ });
}


const bodyOf = (fn: ReturnType<typeof vi.fn>) =>
  (fn.mock.calls[0] as unknown as Array<Record<string, unknown>>).slice(-1)[0] as Record<string, unknown>;

describe('AC-L1 create mode', () => {
  it('AC-L1 step 2 names the section Customer and salesperson and drops the old one', async () => {
    renderForm({ mode: 'create' });
    await toDetails();
    expect(screen.getByRole('button', { name: /^Customer and salesperson/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Lead, customer and salesperson/ })).toBeNull();
  });

  it('AC-L1 has no Lead field and no Create lead option', async () => {
    renderForm({ mode: 'create' });
    await toDetails();
    expect(screen.queryByLabelText(/^Lead/)).toBeNull();
    fireEvent.change(screen.getByLabelText(/^Customer/), { target: { value: 'Pavilion' } });
    expect(screen.queryByRole('button', { name: /Create lead/ })).toBeNull();
    expect(listLeads).not.toHaveBeenCalled();
  });

  it('AC-L1 the section holds Customer then Salesperson, both editable', async () => {
    renderForm({ mode: 'create' });
    await toDetails();
    const customer = within(section()).getByLabelText(/^Customer/);
    const sales = within(section()).getByLabelText('Salesperson');
    expect(customer).toBeEnabled();
    expect(customer.compareDocumentPosition(sales) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('AC-L1 Register stays disabled until a Customer is picked, then sends customer_id and no lead_id key', async () => {
    renderForm({ mode: 'create' });
    await toDetails();
    expect(registerButton()).toBeDisabled();
    await pickCustomer();
    await waitFor(() => expect(registerButton()).toBeEnabled());
    fireEvent.click(registerButton());
    await waitFor(() => expect(registerProject).toHaveBeenCalledTimes(1));
    const body = bodyOf(registerProject);
    expect(body).toMatchObject({ customer_id: 'c-1' });
    expect(body).not.toHaveProperty('lead_id');
  });

  it('AC-L1 the picked Customer stays editable: it can be cleared and Register disables again', async () => {
    renderForm({ mode: 'create' });
    await toDetails();
    await pickCustomer();
    await waitFor(() => expect(registerButton()).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: /^Clear .*customer/i }));
    await waitFor(() => expect(registerButton()).toBeDisabled());
  });

  it('AC-L1 Customer starts empty (nothing fills it for you) and Register is disabled', async () => {
    renderForm({ mode: 'create' });
    await toDetails();
    expect(within(section()).getByLabelText(/^Customer/)).toHaveValue('');
    expect(registerButton()).toBeDisabled();
  });
});

describe('AC-L1 submit-only salesperson', () => {
  beforeEach(() => {
    granted = new Set(['projects.registrations.submit']);
  });

  it('AC-L1 no Lead; Save draft needs no customer, Submit for approval does', async () => {
    renderForm({ mode: 'create' });
    await toDetails();
    expect(screen.queryByLabelText(/^Lead/)).toBeNull();
    expect(screen.getByRole('button', { name: 'Save draft' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Submit for approval' })).toBeDisabled();
    await pickCustomer();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Submit for approval' })).toBeEnabled());
  });

  it('AC-L1 Submit for approval sends customer_id and no lead_id key', async () => {
    renderForm({ mode: 'create' });
    await toDetails();
    await pickCustomer();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Submit for approval' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Submit for approval' }));
    await waitFor(() => expect(registerProject).toHaveBeenCalledTimes(1));
    const body = bodyOf(registerProject);
    expect(body).toMatchObject({ customer_id: 'c-1', submit: true });
    expect(body).not.toHaveProperty('lead_id');
  });

  it('AC-L1 Save draft with no customer sends no lead_id key', async () => {
    renderForm({ mode: 'create' });
    await toDetails();
    fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
    await waitFor(() => expect(registerProject).toHaveBeenCalledTimes(1));
    expect(bodyOf(registerProject)).not.toHaveProperty('lead_id');
  });
});

describe('AC-L5 edit mode', () => {
  it('AC-L5 a project that has a lead shows no Lead field, and the Customer is the editable picker', () => {
    renderForm({ mode: 'edit', project: baseProject() });
    expect(screen.queryByLabelText(/^Lead/)).toBeNull();
    expect(screen.queryByRole('button', { name: /Create lead/ })).toBeNull();
    expect(screen.getByRole('button', { name: /^Customer and salesperson/ })).toBeInTheDocument();
    const picker = screen.getByLabelText(/^Customer/);
    expect(picker).toBeEnabled();
    expect(picker).toHaveValue('KEDAI CONTOH SDN. BHD.');
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeEnabled();
  });

  it('AC-L5 changing the Customer saves it, and the PUT body has no lead_id key', async () => {
    renderForm({ mode: 'edit', project: baseProject() });
    await pickCustomer('KEDAI', 'KEDAI CONTOH SDN. BHD.');
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(updateProject).toHaveBeenCalledTimes(1));
    expect(bodyOf(updateProject)).not.toHaveProperty('lead_id');
  });

  it('AC-L5 clearing the Customer on edit sends customer_id null and no lead_id key (guard)', async () => {
    renderForm({ mode: 'edit', project: baseProject() });
    fireEvent.click(screen.getByRole('button', { name: /^Clear .*customer/i }));
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(updateProject).toHaveBeenCalledTimes(1));
    const body = bodyOf(updateProject);
    expect(body).toHaveProperty('customer_id', null);
    expect(body).not.toHaveProperty('lead_id');
  });

  it('AC-L5 saving an unrelated field sends no lead_id key either', async () => {
    renderForm({ mode: 'edit', project: baseProject() });
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(updateProject).toHaveBeenCalledTimes(1));
    expect(bodyOf(updateProject)).not.toHaveProperty('lead_id');
  });

  it('AC-L5 a project with no lead has the same editable picker', () => {
    renderForm({ mode: 'edit', project: baseProject({ lead_id: null, lead_code: null, lead_title: null }) });
    expect(screen.queryByLabelText(/^Lead/)).toBeNull();
    expect(screen.getByLabelText(/^Customer/)).toBeEnabled();
  });
});
