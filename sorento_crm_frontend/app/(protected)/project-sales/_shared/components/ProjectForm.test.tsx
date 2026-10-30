/**
 * ProjectForm, the one component both /project-sales/new and /project-sales/<id>/edit
 * render (PLAN-project-form-28sep.md, UAC project-form-28sep-acceptance-criteria.md).
 *
 * Red before the coder: this component does not exist yet. Every test here is written
 * against the contract in the plan and the captain's test list, not against any
 * implementation.
 *
 * SearchableSelect, SearchableMultiSelect and DateRangePicker are mocked to plain form
 * controls so the tests exercise ProjectForm's own wiring (which prop goes to which
 * field, what gets submitted) rather than Radix/cmdk popover mechanics, which those
 * components' own test files already cover.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ClashCandidate, Project } from '../types/project.types';

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

const hasManagePermission = vi.fn(() => true);
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => hasManagePermission(slug),
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

import { ProjectForm } from './ProjectForm';

const DEVELOPER = { id: 'd1', party_type: 'developer', name: 'SP Setia', is_active: true };
const ARCHITECT = { id: 'a1', party_type: 'architect', name: 'Archico', is_active: true };
const CONTRACTOR = {
  id: 'c1',
  party_type: 'main_contractor',
  name: 'BuildIt',
  is_active: true,
};
const TYPE_LAUNCH = {
  id: 'ty1',
  name: 'Property',
  code: 'PROP',
  derives_delivery_from_launch: true,
  sort_order: 1,
  is_active: true,
};
const TYPE_NO_LAUNCH = {
  id: 'ty2',
  name: 'Hotel',
  code: 'HOTEL',
  derives_delivery_from_launch: false,
  sort_order: 2,
  is_active: true,
};
const LEAD_OPEN = {
  id: 'lead-1',
  lead_code: 'LEAD-000001',
  title: 'Menara Lead',
  outcome: 'open',
  customer_id: 'cust-1',
  customer_name: 'Aman Hartanah',
  owner_user_id: 'u-me',
  project_count: 0,
  possible_duplicates: [],
  can_edit: true,
};

const BLOCKING: ClashCandidate = {
  project_id: 'p9',
  project_code: 'PRJ-000009',
  title: 'Setia Alam Phase 3B',
  outcome: 'open',
  similarity: 1,
  blocks: true,
};

function baseProject(overrides: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    project_code: 'PRJ-000001',
    title: 'Setia Alam Phase 3B',
    outcome: 'open',
    is_critical: false,
    developer_party_id: 'd1',
    developer_name: 'SP Setia',
    type_id: 'ty2',
    type_name: 'Hotel',
    template_id: null,
    template_name: null,
    owner_user_id: 'u-2',
    owner_name: 'Aina',
    registered_company_name: 'Setia SPV Sdn Bhd',
    location: 'Setia Alam, Selangor',
    address: '123 Jalan Setia',
    admin_ref: 'PS26-0001',
    estimated_sales_value: '1000000',
    launch_date: null,
    expected_delivery_from: '2027-01-01',
    expected_delivery_to: '2027-06-01',
    architect_party_id: 'a1',
    architect_name: 'Archico',
    main_contractor_party_id: 'c1',
    main_contractor_name: 'BuildIt',
    lead_id: 'lead-9',
    lead_code: 'LEAD-000009',
    next_action_overdue: false,
    stale_level: 0,
    is_unattended: false,
    open_task_count: 0,
    can_edit: true,
    ...overrides,
  } as Project;
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

/** Developer, Architect, Main contractor and Customer are async searches: type, then pick. */
async function pickParty(label: string | RegExp, text: string, optionName: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value: text } });
  fireEvent.click(await screen.findByRole('button', { name: optionName }));
}

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

async function fillWho() {
  await pickParty('Developer', 'SP', 'SP Setia');
  fireEvent.change(screen.getByLabelText(/project title/i), {
    target: { value: 'Setia Alam Phase 3B' },
  });
  fireEvent.blur(screen.getByLabelText(/project title/i));
  await toDetails();
  await waitFor(() =>
    expect(within(screen.getByLabelText('Project type')).getByText('Hotel')).toBeInTheDocument(),
  );
  fireEvent.change(screen.getByLabelText('Project type'), { target: { value: 'ty2' } });
  // Details opens by itself once the template list for the type has answered.
  await waitFor(() =>
    expect(screen.getByRole('button', { name: /^Details/ })).toHaveAttribute(
      'aria-expanded',
      'true',
    ),
  );
}

/** AC-L1: a new project's Customer is the search picker; nothing fills it from a lead. */
async function pickCustomer() {
  await pickParty(/^Customer/, 'Aman', 'Aman Hartanah');
}

/** Details starts folded in create mode (AC-PF033); open it by hand for its fields. */
function openDetails() {
  const header = screen.getByRole('button', { name: /^Details/ });
  if (header.getAttribute('aria-expanded') !== 'true') fireEvent.click(header);
}

async function pickType(typeId: string, typeName: string) {
  await waitFor(() =>
    expect(within(screen.getByLabelText('Project type')).getByText(typeName)).toBeInTheDocument(),
  );
  fireEvent.change(screen.getByLabelText('Project type'), { target: { value: typeId } });
}

beforeEach(() => {
  vi.clearAllMocks();
  sessionUser = { id: 'u-me', name: 'Me' };
  hasManagePermission.mockReturnValue(true);
  listParties.mockImplementation(async (params: { party_type?: string }) => {
    const byType: Record<string, unknown[]> = {
      developer: [DEVELOPER],
      architect: [ARCHITECT],
      main_contractor: [CONTRACTOR],
    };
    return {
      data: byType[params.party_type ?? ''] ?? [],
      pagination: { total: 1, page: 1, limit: 200 },
    };
  });
  listProjectTypes.mockResolvedValue([TYPE_LAUNCH, TYPE_NO_LAUNCH]);
  listProjectTemplates.mockResolvedValue([]);
  previewClashes.mockResolvedValue({ candidates: [], would_block: false });
  registerProject.mockResolvedValue({ id: 'new1', project_code: 'PRJ-000099' });
  updateProject.mockResolvedValue(baseProject());
  listLeads.mockResolvedValue({ data: [LEAD_OPEN], pagination: { total: 1, page: 1, limit: 20 } });
  getUserLookup.mockResolvedValue([
    { id: 'u-me', name: 'Me' },
    { id: 'u-2', name: 'Aina' },
  ]);
  listCustomerOptions.mockResolvedValue([{ value: 'cust-1', label: 'Aman Hartanah' }]);
  getLead.mockImplementation(async (id: string) => ({ ...LEAD_OPEN, id }));
});

describe('ProjectForm: sections (AC-PF033, AC-PF034)', () => {
  it('create mode opens Who and what and Customer and salesperson, collapses Details', async () => {
    renderForm({ mode: 'create' });
    await toDetails();
    expect(screen.getByRole('button', { name: /Who and what/ })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
    expect(screen.getByRole('button', { name: /^Details/ })).toHaveAttribute(
      'aria-expanded',
      'false',
    );
    expect(screen.getByRole('button', { name: /^Customer and salesperson/ })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
  });

  it('edit mode opens every section', () => {
    renderForm({ mode: 'edit', project: baseProject() });
    for (const name of [/Who and what/, /^Details/, /^Customer and salesperson/]) {
      expect(screen.getByRole('button', { name })).toHaveAttribute('aria-expanded', 'true');
    }
  });

  it('opens Details by itself once Who and what is filled, then never reopens it by hand', async () => {
    renderForm({ mode: 'create' });
    await fillWho();
    await waitFor(() => expect(screen.getByLabelText('Location')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /^Details/ })).toHaveAttribute(
      'aria-expanded',
      'true',
    );

    fireEvent.click(screen.getByRole('button', { name: /^Details/ }));
    expect(screen.queryByLabelText('Location')).toBeNull();

    // The title lives on the Check step now: go back, change it, Check and come forward again.
    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
    fireEvent.change(screen.getByLabelText(/project title/i), {
      target: { value: 'Setia Alam Phase 3C' },
    });
    fireEvent.blur(screen.getByLabelText(/project title/i));
    await toDetails();
    expect(screen.queryByLabelText('Location')).toBeNull();
  });
});

describe('ProjectForm: primary CTA (AC-PF007)', () => {
  it('renders exactly one submit button', async () => {
    const { container } = renderForm({ mode: 'create' });
    await toDetails();
    expect(container.querySelectorAll('button[type="submit"]').length).toBe(1);
  });

  it('labels the CTA Register project on create and Save changes on edit', async () => {
    renderForm({ mode: 'create' });
    await toDetails();
    expect(screen.getByRole('button', { name: 'Register project' })).toBeInTheDocument();

    renderForm({ mode: 'edit', project: baseProject() });
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeInTheDocument();
  });

  it('disables submit while the title is empty (AC-PF010)', async () => {
    renderForm({ mode: 'create' });
    await toDetails();
    expect(screen.getByRole('button', { name: 'Register project' })).toBeDisabled();
  });
});

describe('ProjectForm: Cancel (AC-PF007)', () => {
  it('returns to the pipeline on create', () => {
    renderForm({ mode: 'create' });
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(push).toHaveBeenCalledWith('/project-sales/pipeline');
  });

  it('returns to the project on edit', () => {
    renderForm({ mode: 'edit', project: baseProject() });
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(push).toHaveBeenCalledWith('/project-sales/p1');
  });
});

describe('ProjectForm: Check button (AC-PF030, AC-PF031)', () => {
  it('is disabled below 4 characters', () => {
    renderForm({ mode: 'create' });
    const check = screen.getByRole('button', { name: 'Check' });
    expect(check).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/project title/i), { target: { value: 'Set' } });
    expect(check).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/project title/i), { target: { value: 'Seti' } });
    expect(check).toBeEnabled();
  });

  it('runs no duplicate check while typing', async () => {
    renderForm({ mode: 'create' });
    for (const value of ['Seti', 'Setia', 'Setia Alam Phase 3B']) {
      fireEvent.change(screen.getByLabelText(/project title/i), { target: { value } });
    }
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
    expect(previewClashes).not.toHaveBeenCalled();
  });

  it('Check runs the check exactly once', async () => {
    renderForm({ mode: 'create' });
    fireEvent.change(screen.getByLabelText(/project title/i), {
      target: { value: 'Setia Alam Phase 3B' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Check' }));
    await waitFor(() => expect(previewClashes).toHaveBeenCalledTimes(1));
    fireEvent.click(await screen.findByRole('button', { name: 'Next' }));
    await pickCustomer();
    expect(screen.getByRole('button', { name: 'Register project' })).toBeEnabled();
  });

  it('AC-R2 a blocking match shows one line and turns the CTA into Register as secondary lead', async () => {
    previewClashes.mockResolvedValue({ candidates: [BLOCKING], would_block: true });
    renderForm({ mode: 'create' });
    fireEvent.change(screen.getByLabelText(/project title/i), {
      target: { value: 'Setia Alam Phase 3B' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Check' }));
    const cta = await screen.findByRole('button', { name: 'Register as secondary lead on PRJ-000009' });
    expect(cta).toBeEnabled();
    expect(screen.getByText(/Clash:/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Register project' })).toBeNull();
    expect(screen.queryByText('Blocked by an existing project')).toBeNull();
  });

  it('submit re-runs the check once as a guard before registering (AC-PF031)', async () => {
    renderForm({ mode: 'create' });
    await fillWho();
    await pickCustomer();
    previewClashes.mockClear(); // fillWho pressed Check; count only the submit guard
    fireEvent.click(screen.getByRole('button', { name: 'Register project' }));
    await waitFor(() => expect(registerProject).toHaveBeenCalledTimes(1));
    expect(previewClashes).toHaveBeenCalledTimes(1);
  });

  it('a submit-time blocking match stops the register call', async () => {
    renderForm({ mode: 'create' });
    await fillWho();
    await pickCustomer();
    // The Check step passed; the clash appears between Check and Register.
    previewClashes.mockResolvedValue({ candidates: [BLOCKING], would_block: true });
    previewClashes.mockClear();
    fireEvent.click(screen.getByRole('button', { name: 'Register project' }));
    await waitFor(() => expect(previewClashes).toHaveBeenCalledTimes(1));
    expect(registerProject).not.toHaveBeenCalled();
  });
});

describe('ProjectForm: type drives To-do list template and delivery fields (AC-PF015, PF016, PF019, PF020)', () => {
  it('shows To-do list template only once a type is chosen', () => {
    renderForm({ mode: 'create' });
    expect(screen.queryByLabelText('To-do list template')).toBeNull();
  });

  it('clears To-do list template when the type changes', async () => {
    listProjectTemplates.mockResolvedValue([
      { id: 'tp1', name: 'Standard', has_forked_status_graph: false },
    ]);
    renderForm({ mode: 'create' });
    await toDetails();
    await pickType('ty2', 'Hotel');
    await waitFor(() =>
      expect(within(screen.getByLabelText('To-do list template')).getByText('Standard')).toBeInTheDocument(),
    );
    fireEvent.change(screen.getByLabelText('To-do list template'), { target: { value: 'tp1' } });
    fireEvent.change(screen.getByLabelText('Project type'), { target: { value: 'ty1' } });
    await waitFor(() =>
      expect((screen.getByLabelText('To-do list template') as HTMLSelectElement).value).toBe(''),
    );
  });

  it('shows Project launch date for a type that derives delivery from launch', async () => {
    renderForm({ mode: 'create' });
    await toDetails();
    await pickType('ty1', TYPE_LAUNCH.name);
    openDetails();
    await waitFor(() => expect(screen.getByLabelText('Project launch date')).toBeInTheDocument());
    expect(screen.queryByLabelText('Expected delivery')).toBeNull();
  });

  it('shows Expected delivery for a type that does not derive delivery from launch', async () => {
    renderForm({ mode: 'create' });
    await toDetails();
    await pickType('ty2', 'Hotel');
    openDetails();
    await waitFor(() => expect(screen.getByLabelText('Expected delivery')).toBeInTheDocument());
    expect(screen.queryByLabelText('Project launch date')).toBeNull();
  });
});

describe('ProjectForm: clearable selects (AC-PF011, PF015, PF022, PF023)', () => {
  it('Developer clears back to empty', async () => {
    renderForm({ mode: 'create' });
    await pickParty('Developer', 'SP', 'SP Setia');
    expect((screen.getByLabelText('Developer') as HTMLInputElement).value).toBe('SP Setia');
    fireEvent.click(screen.getByRole('button', { name: 'Clear project-developer' }));
    expect((screen.getByLabelText('Developer') as HTMLInputElement).value).toBe('');
    expect(screen.queryByRole('button', { name: 'Clear project-developer' })).toBeNull();
  });
});

describe('ProjectForm: text and number fields (AC-PF012-014, PF017, PF018)', () => {
  it('limits Reference to 64 characters', async () => {
    renderForm({ mode: 'create' });
    await toDetails();
    openDetails();
    expect(screen.getByLabelText('Reference')).toHaveAttribute('maxLength', '64');
  });

  it('Estimated sales value is a non-negative number field', async () => {
    renderForm({ mode: 'create' });
    await toDetails();
    openDetails();
    const input = screen.getByLabelText('Estimated sales value (RM)');
    expect(input).toHaveAttribute('type', 'number');
    expect(input).toHaveAttribute('min', '0');
  });

  it('renders Address as a text field', async () => {
    renderForm({ mode: 'create' });
    await fillWho();
    await waitFor(() => expect(screen.getByLabelText('Address')).toBeInTheDocument());
  });
});

describe('ProjectForm: Brands are gone (PROJECT-REGISTER-V2 G3)', () => {
  it('has no Brands field on create or edit', () => {
    renderForm({ mode: 'create' });
    expect(screen.queryByLabelText('Brands')).toBeNull();
    renderForm({ mode: 'edit', project: baseProject() });
    expect(screen.queryByLabelText('Brands')).toBeNull();
  });

  it('sends no brand_ids on create', async () => {
    renderForm({ mode: 'create' });
    await fillWho();
    await pickCustomer();
    fireEvent.click(screen.getByRole('button', { name: 'Register project' }));
    await waitFor(() => expect(registerProject).toHaveBeenCalled());
    expect(registerProject.mock.calls[0][0]).not.toHaveProperty('brand_ids');
  });
});

describe('ProjectForm: Salesperson (AC-PF040-043)', () => {
  it('defaults to the current session user on create', async () => {
    renderForm({ mode: 'create' });
    await toDetails();
    await waitFor(() => expect(getUserLookup).toHaveBeenCalled());
    await waitFor(() =>
      expect((screen.getByLabelText('Salesperson') as HTMLSelectElement).value).toBe('u-me'),
    );
  });

  it('defaults to the current owner on edit', async () => {
    renderForm({ mode: 'edit', project: baseProject({ owner_user_id: 'u-2' }) });
    await waitFor(() =>
      expect((screen.getByLabelText('Salesperson') as HTMLSelectElement).value).toBe('u-2'),
    );
  });

  it('is disabled without manage permission', async () => {
    hasManagePermission.mockReturnValue(false);
    renderForm({ mode: 'create' });
    await toDetails();
    await waitFor(() => expect(screen.getByLabelText('Salesperson')).toBeDisabled());
  });

  it('lets a manage holder pick another salesperson on create, sent as owner_user_id', async () => {
    renderForm({ mode: 'create' });
    await fillWho();
    await pickCustomer();
    await waitFor(() => expect(screen.getByLabelText('Salesperson')).not.toBeDisabled());
    fireEvent.change(screen.getByLabelText('Salesperson'), { target: { value: 'u-2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Register project' }));
    await waitFor(() =>
      expect(registerProject).toHaveBeenCalledWith(
        expect.objectContaining({ owner_user_id: 'u-2' }),
      ),
    );
  });
});

describe('ProjectForm: no lead on registration (AC-L1)', () => {
  it('AC-L1 will not register a project without a customer', async () => {
    renderForm({ mode: 'create' });
    await fillWho();
    expect(screen.getByRole('button', { name: 'Register project' })).toBeDisabled();
    await pickCustomer();
    expect(screen.getByRole('button', { name: 'Register project' })).toBeEnabled();
  });

  it('AC-L1 shows no Lead field and no Create lead option, in create or edit', async () => {
    renderForm({ mode: 'create' });
    await toDetails();
    expect(screen.queryByLabelText(/^Lead/)).toBeNull();
    expect(screen.queryByRole('button', { name: /Create lead/ })).toBeNull();
    cleanup();
    renderForm({ mode: 'edit', project: baseProject() });
    expect(screen.queryByLabelText(/^Lead/)).toBeNull();
  });

  it('AC-L1 the register body carries the picked customer_id and no lead_id key', async () => {
    renderForm({ mode: 'create' });
    await fillWho();
    await pickCustomer();
    fireEvent.click(screen.getByRole('button', { name: 'Register project' }));
    await waitFor(() => expect(registerProject).toHaveBeenCalledTimes(1));
    const body = registerProject.mock.calls[0][0] as Record<string, unknown>;
    expect(body).toMatchObject({ customer_id: 'cust-1' });
    expect(body).not.toHaveProperty('lead_id');
  });

  it('AC-L5 an edit never sends lead_id, even for a project that has a lead', async () => {
    renderForm({ mode: 'edit', project: baseProject({ lead_id: 'lead-9', lead_code: 'LEAD-000009' }) });
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(updateProject).toHaveBeenCalledTimes(1));
    expect(updateProject.mock.calls[0][1]).not.toHaveProperty('lead_id');
  });
});

describe('ProjectForm: create submit (AC-PF024)', () => {
  it('registers with the filled fields and navigates to the new project', async () => {
    renderForm({ mode: 'create' });
    await fillWho();
    await pickCustomer();
    fireEvent.change(screen.getByLabelText('Registered company / SPV'), {
      target: { value: 'Setia SPV' },
    });
    fireEvent.change(screen.getByLabelText('Location'), { target: { value: 'Setia Alam' } });
    fireEvent.change(screen.getByLabelText('Address'), {
      target: { value: '123 Jalan Setia' },
    });
    fireEvent.change(screen.getByLabelText('Reference'), {
      target: { value: 'PS26-0099' },
    });
    fireEvent.change(screen.getByLabelText('Estimated sales value (RM)'), {
      target: { value: '500000' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Register project' }));

    await waitFor(() =>
      expect(registerProject).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Setia Alam Phase 3B',
          developer_party_id: 'd1',
          type_id: 'ty2',
          registered_company_name: 'Setia SPV',
          location: 'Setia Alam',
          address: '123 Jalan Setia',
          admin_ref: 'PS26-0099',
          estimated_sales_value: '500000',
          customer_id: 'cust-1',
        }),
      ),
    );
    await waitFor(() => expect(push).toHaveBeenCalledWith('/project-sales/new1'));
  });
});

describe('ProjectForm: edit submit (AC-PF025)', () => {
  it('saves the edited fields and navigates back to the project', async () => {
    renderForm({ mode: 'edit', project: baseProject() });
    fireEvent.change(screen.getByLabelText('Location'), { target: { value: 'New Location' } });

    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

    await waitFor(() =>
      expect(updateProject).toHaveBeenCalledWith(
        'p1',
        expect.objectContaining({ location: 'New Location' }),
      ),
    );
    await waitFor(() => expect(push).toHaveBeenCalledWith('/project-sales/p1'));
  });

  it('sends null for an optional text field that was cleared', async () => {
    renderForm({
      mode: 'edit',
      project: baseProject({ registered_company_name: 'Setia SPV' }),
    });
    fireEvent.change(screen.getByLabelText('Registered company / SPV'), {
      target: { value: '' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

    await waitFor(() =>
      expect(updateProject).toHaveBeenCalledWith(
        'p1',
        expect.objectContaining({ registered_company_name: null }),
      ),
    );
  });
});

describe('ProjectForm: edit guards (review round 1, PR #1345)', () => {
  const blockingMatch = (projectId: string): ClashCandidate => ({
    project_id: projectId,
    project_code: `PRJ-${projectId}`,
    title: 'Setia Alam Phase 3B',
    outcome: 'open',
    similarity: 1,
    blocks: true,
  });

  it('keeps the project template when the edit form opens under StrictMode (AC-PF015, PF025)', async () => {
    listProjectTemplates.mockResolvedValue([
      { id: 'tp1', name: 'Standard', has_forked_status_graph: false },
    ]);
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <React.StrictMode>
        <QueryClientProvider client={client}>
          <ProjectForm mode="edit" project={baseProject({ template_id: 'tp1' })} />
        </QueryClientProvider>
      </React.StrictMode>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

    await waitFor(() =>
      expect(updateProject).toHaveBeenCalledWith(
        'p1',
        expect.objectContaining({ template_id: 'tp1' }),
      ),
    );
  });

  it('saves an unrelated field without running the clash guard (AC-PF032)', async () => {
    previewClashes.mockResolvedValue({ candidates: [blockingMatch('p9')], would_block: true });
    renderForm({ mode: 'edit', project: baseProject() });
    fireEvent.change(screen.getByLabelText('Location'), { target: { value: 'Puchong' } });

    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

    await waitFor(() =>
      expect(updateProject).toHaveBeenCalledWith(
        'p1',
        expect.objectContaining({ location: 'Puchong' }),
      ),
    );
    expect(previewClashes).not.toHaveBeenCalled();
  });

  it('a rename matching only the project itself is not blocked (AC-PF032)', async () => {
    previewClashes.mockResolvedValue({ candidates: [blockingMatch('p1')], would_block: true });
    renderForm({ mode: 'edit', project: baseProject() });
    fireEvent.change(screen.getByLabelText(/project title/i), {
      target: { value: 'Setia Alam Phase 3B Tower' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

    await waitFor(() =>
      expect(updateProject).toHaveBeenCalledWith(
        'p1',
        expect.objectContaining({ title: 'Setia Alam Phase 3B Tower' }),
      ),
    );
    expect(previewClashes).toHaveBeenCalled();
    expect(screen.queryByText(/Clash:/)).toBeNull();
  });

  it('a rename onto another project is still blocked (AC-PF032)', async () => {
    previewClashes.mockResolvedValue({ candidates: [blockingMatch('p9')], would_block: true });
    renderForm({ mode: 'edit', project: baseProject() });
    fireEvent.change(screen.getByLabelText(/project title/i), {
      target: { value: 'Setia Alam Phase 3B Tower' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled(),
    );
    expect(screen.getByText(/Clash:/)).toBeInTheDocument();
    expect(updateProject).not.toHaveBeenCalled();
  });
});
