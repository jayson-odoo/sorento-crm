/**
 * PS-REGISTRATION-V3 on the register form: party links (several subcontractors / trading
 * houses / tender parties, one consultant / interior designer), contacts picked per party,
 * Area from the district list of the picked State, Location on edit only.
 * Card: documentation/plans/projects/CARD-ps-registration-v3-02nov.md (rules 1-9).
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
    listPartyRoles: async () => ROLES,
    getPartiesOnProject: async () => [],
    listProjectTypes: (...args: unknown[]) => listProjectTypes(...args),
    listProjectTemplates: (...args: unknown[]) => listProjectTemplates(...args),
    previewClashes: (...args: unknown[]) => previewClashes(...args),
    registerProject: (...args: unknown[]) => registerProject(...args),
    updateProject: (...args: unknown[]) => updateProject(...args),
    listLeads: (...args: unknown[]) => listLeads(...args),
    getLead: (...args: unknown[]) => getLead(...args),
    listCustomerOptions: (...args: unknown[]) => listCustomerOptions(...args),
    listPartyContacts: (...args: unknown[]) => listPartyContacts(...args),
  };
});

const listPartyContacts = vi.fn();

// PROJECT-PARTY-ROLES: the party roles are a lookup list (seed order).
const ROLES = [
  { value: 'developer', label: 'Developer', is_active: true, allows_many: false },
  { value: 'architect', label: 'Architect', is_active: true, allows_many: false },
  { value: 'main_contractor', label: 'Main contractor', is_active: true, allows_many: false },
  { value: 'trading_house', label: 'Trading house', is_active: true, allows_many: true },
  { value: 'subcontractor', label: 'Subcontractor', is_active: true, allows_many: true },
  { value: 'tender_party', label: 'Tender party', is_active: true, allows_many: true },
  { value: 'consultant', label: 'Consultant', is_active: true, allows_many: false },
  { value: 'interior_designer', label: 'Interior designer', is_active: true, allows_many: false },
];
const lookupKeys: string[] = [];

type Option = { value: string; label: string };

// PS-REGISTRATION-V3: the lead source and district lists are lookup sets.
vi.mock('@/hooks/useLookupSetOptions', () => ({
  useLookupSetOptions: (key: string) => (lookupKeys.push(key), {
    data:
      key === 'project_lead_source'
        ? [{ value: 'site_visit', label: 'Site visit' }]
        : key.startsWith('my_district_')
          ? [{ value: 'Petaling', label: 'Petaling' }]
          : [{ value: 'Selangor', label: 'Selangor' }],
    error: null,
    refetch: vi.fn(),
  }),
}));

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

// A plain stand-in: async results and static options as "pick" buttons, picks as chips.
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({
    id,
    value,
    onChange,
    options,
    fetchOptions,
  }: {
    id?: string;
    value: string[];
    onChange: (next: string[]) => void;
    options?: Option[];
    fetchOptions?: (query: string, page: number) => Promise<Option[]>;
  }) => {
    const [results, setResults] = React.useState<Option[]>([]);
    const shown = fetchOptions ? results : (options ?? []);
    return (
      <span>
        <input
          id={id}
          onChange={(event) => void fetchOptions?.(event.target.value, 0).then(setResults)}
        />
        {shown
          .filter((o) => !value.includes(o.value))
          .map((o) => (
            <button key={o.value} type="button" onClick={() => onChange([...value, o.value])}>
              pick {o.label}
            </button>
          ))}
        {value.map((v) => (
          <button key={v} type="button" onClick={() => onChange(value.filter((x) => x !== v))}>
            unpick {v}
          </button>
        ))}
      </span>
    );
  },
}));

import { ProjectForm } from './ProjectForm';

// Any party can fill any role, so the search sees every party (filtered by the query only).
const PARTIES: { id: string; name: string; party_type: string }[] = [
  { id: 'd1', name: 'SP Setia', party_type: 'developer' },
  { id: 'a1', name: 'Archico', party_type: 'architect' },
  { id: 'c1', name: 'BuildIt', party_type: 'main_contractor' },
  { id: 's1', name: 'Sub One', party_type: 'subcontractor' },
  { id: 's2', name: 'Sub Two', party_type: 'subcontractor' },
  { id: 't1', name: 'Trade House', party_type: 'trading_house' },
  { id: 'tp1', name: 'Tender Co', party_type: 'tender_party' },
  { id: 'q1', name: 'QS Firm', party_type: 'consultant' },
  { id: 'i1', name: 'ID Studio', party_type: 'interior_designer' },
];

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

async function pickParty(label: string | RegExp, text: string, optionName: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value: text } });
  fireEvent.click(await screen.findByRole('button', { name: optionName }));
}

async function pickMany(label: string | RegExp, optionName: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value: optionName } });
  fireEvent.click(await screen.findByRole('button', { name: `pick ${optionName}` }));
}

/** Opens the contacts popup of the only picked party, ticks one contact and presses Done. */
async function tickContact(name: string) {
  fireEvent.click(await screen.findByRole('button', { name: 'Add contacts' }));
  const dialog = await screen.findByRole('dialog');
  // The popup's picker is SearchableMultiSelect, whose stand-in above lists "pick <name>" buttons;
  // a party's only contact is preselected, so it may already be picked.
  await waitFor(() => expect(within(dialog).queryByText('Loading contacts')).toBeNull());
  const pick = within(dialog).queryByRole('button', { name: `pick ${name}` });
  if (pick) fireEvent.click(pick);
  fireEvent.click(within(dialog).getByRole('button', { name: 'Done' }));
}

async function toDetails() {
  fireEvent.change(screen.getByLabelText(/project title/i), {
    target: { value: 'Residensi Contoh Phase 2' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Check' }));
  await screen.findByText('No clash');
  fireEvent.click(screen.getByRole('button', { name: 'Next' }));
  await screen.findByRole('button', { name: /^Parties and contacts/ });
  fireEvent.change(screen.getByLabelText(/^Lead source/), { target: { value: 'site_visit' } });
}

function register() {
  fireEvent.click(screen.getByRole('button', { name: 'Register project' }));
}

const lastBody = () =>
  registerProject.mock.calls.at(-1)?.[0] as Record<string, unknown> | undefined;

function project(overrides: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    project_code: 'PPF2611001',
    title: 'Residensi Contoh Phase 2',
    outcome: 'open',
    is_critical: false,
    developer_party_id: 'd1',
    developer_name: 'SP Setia',
    owner_user_id: 'u-me',
    owner_name: 'Me',
    location: 'Old typed location',
    state: 'Selangor',
    mukim: 'Typed area',
    lead_source: 'dealer',
    party_links: [
      { role: 'subcontractor', party_id: 's1', name: 'Sub One' },
      { role: 'consultant', party_id: 'q1', name: 'QS Firm' },
    ],
    next_action_overdue: false,
    stale_level: 0,
    is_unattended: false,
    open_task_count: 0,
    can_edit: true,
    ...overrides,
  } as Project;
}

beforeEach(() => {
  vi.clearAllMocks();
  lookupKeys.length = 0;
  sessionUser = { id: 'u-me', name: 'Me' };
  hasManagePermission.mockReturnValue(true);
  listParties.mockImplementation(async (params: { query?: string }) => ({
    data: PARTIES.filter((p) => p.name.toLowerCase().includes((params.query ?? '').toLowerCase())).map(
      (p) => ({ ...p, is_active: true }),
    ),
    pagination: { total: 1, page: 1, limit: 20 },
  }));
  listProjectTypes.mockResolvedValue([]);
  listProjectTemplates.mockResolvedValue([]);
  previewClashes.mockResolvedValue({ candidates: [], would_block: false });
  registerProject.mockResolvedValue({ id: 'new1', project_code: 'PPF2611002' });
  updateProject.mockResolvedValue(project());
  getUserLookup.mockResolvedValue([{ id: 'u-me', name: 'Me' }]);
  listCustomerOptions.mockResolvedValue([]);
  listPartyContacts.mockImplementation(async (partyId: string) =>
    partyId === 'a1'
      ? [{ id: 'k1', party_id: 'a1', name: 'Ar. Example One', is_active: true }]
      : partyId === 's1'
        ? [{ id: 'k2', party_id: 's1', name: 'Site Example', is_active: true }]
        : [],
  );
});

describe('PS-REGISTRATION-V3 party links (Q5 b)', () => {
  it('sends several subcontractors and one consultant as party_links', async () => {
    renderForm({ mode: 'create' });
    await toDetails();
    await pickMany('Subcontractor', 'Sub One');
    await pickMany('Subcontractor', 'Sub Two');
    await pickParty('Consultant', 'QS', 'QS Firm');
    register();
    await waitFor(() => expect(lastBody()).toBeTruthy());
    expect(lastBody()!.party_links).toEqual([
      { role: 'subcontractor', party_id: 's1' },
      { role: 'subcontractor', party_id: 's2' },
      { role: 'consultant', party_id: 'q1' },
    ]);
  });

  it('offers every new role on the form', async () => {
    renderForm({ mode: 'create' });
    await toDetails();
    for (const label of [
      'Subcontractor',
      'Trading house',
      'Tender party',
      'Consultant',
      'Interior designer',
    ]) {
      expect(screen.getByLabelText(label)).toBeInTheDocument();
    }
  });

  it('edit shows the stored links and sends them back unchanged', async () => {
    renderForm({ mode: 'edit', project: project() });
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(updateProject).toHaveBeenCalledTimes(1));
    const body = updateProject.mock.calls[0][1] as Record<string, unknown>;
    expect(body.party_links).toEqual([
      { role: 'subcontractor', party_id: 's1' },
      { role: 'consultant', party_id: 'q1' },
    ]);
    expect(body.lead_source).toBe('dealer');
  });
});

describe('PS-REGISTRATION-V3 contacts picked per party (rules 5-7)', () => {
  it('a picked party with one contact has it ticked and sent as contact_ids (owner, 10 Nov)', async () => {
    renderForm({ mode: 'create' });
    await toDetails();
    await pickParty('Architect', 'Arch', 'Archico');
    // Its only contact is ticked without opening the popup.
    await screen.findByRole('button', { name: '1 contact' });
    register();
    await waitFor(() => expect(lastBody()).toBeTruthy());
    expect(lastBody()!.contact_ids).toEqual(['k1']);
  });

  it('a party picked through a link gets its own contacts picker', async () => {
    renderForm({ mode: 'create' });
    await toDetails();
    await pickMany('Subcontractor', 'Sub One');
    await screen.findByRole('button', { name: '1 contact' });
    register();
    await waitFor(() => expect(lastBody()).toBeTruthy());
    expect(lastBody()!.contact_ids).toEqual(['k2']);
  });

  it('clearing a party and picking it again re-applies its single contact (owner re-test 10 Nov)', async () => {
    renderForm({ mode: 'create' });
    await toDetails();
    await pickParty('Architect', 'Arch', 'Archico');
    await screen.findByRole('button', { name: '1 contact' });
    fireEvent.click(screen.getByRole('button', { name: 'Clear project-party-architect' }));
    await pickParty('Architect', 'Arch', 'Archico');
    await screen.findByRole('button', { name: '1 contact' });
    register();
    await waitFor(() => expect(lastBody()).toBeTruthy());
    expect(lastBody()!.contact_ids).toEqual(['k1']);
  });

  it('clearing the party drops its contact picks', async () => {
    renderForm({ mode: 'create' });
    await toDetails();
    await pickParty('Architect', 'Arch', 'Archico');
    await tickContact('Ar. Example One');
    fireEvent.click(screen.getByRole('button', { name: 'Clear project-party-architect' }));
    register();
    await waitFor(() => expect(lastBody()).toBeTruthy());
    expect(lastBody()).not.toHaveProperty('contact_ids');
  });

  it('edit offers the contacts link and sends picked contact_ids', async () => {
    renderForm({
      mode: 'edit',
      project: project({
        developer_party_id: null,
        developer_name: null,
        party_links: [{ role: 'architect', party_id: 'a1', name: 'Archico' }],
      }),
    });
    await tickContact('Ar. Example One');
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(updateProject).toHaveBeenCalledTimes(1));
    const body = updateProject.mock.calls[0][1] as Record<string, unknown>;
    expect(body.contact_ids).toEqual(['k1']);
  });

  it('edit: a party already on the project, cleared and picked again, gets its single contact', async () => {
    renderForm({
      mode: 'edit',
      project: project({
        developer_party_id: null,
        developer_name: null,
        party_links: [{ role: 'architect', party_id: 'a1', name: 'Archico' }],
      }),
    });
    await screen.findByRole('button', { name: 'Add contacts' });
    fireEvent.click(screen.getByRole('button', { name: 'Clear project-party-architect' }));
    await pickParty('Architect', 'Arch', 'Archico');
    await screen.findByRole('button', { name: '1 contact' });
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(updateProject).toHaveBeenCalledTimes(1));
    expect((updateProject.mock.calls[0][1] as Record<string, unknown>).contact_ids).toEqual(['k1']);
  });
});

describe('PS-REGISTRATION-V3 Area and Location (rules 1-2, Q3 a)', () => {
  it('Area waits for a State, then reads that state\'s district list', async () => {
    renderForm({ mode: 'create' });
    await toDetails();
    fireEvent.click(screen.getByRole('button', { name: /^Details/ }));
    expect(screen.getByLabelText('Area')).toBeDisabled();
    fireEvent.change(screen.getByLabelText('State'), { target: { value: 'Selangor' } });
    expect(screen.getByLabelText('Area')).toBeEnabled();
    expect(lookupKeys).toContain('my_district_selangor');
    fireEvent.change(screen.getByLabelText('Area'), { target: { value: 'Petaling' } });
    register();
    await waitFor(() => expect(lastBody()).toBeTruthy());
    expect(lastBody()).toMatchObject({ state: 'Selangor', mukim: 'Petaling' });
  });

  it('an area typed before the list existed still shows as itself on edit', () => {
    renderForm({ mode: 'edit', project: project() });
    expect(screen.getByLabelText('Area')).toHaveValue('Typed area');
  });

  it('the register form has no Location; edit still shows the stored one', () => {
    renderForm({ mode: 'edit', project: project() });
    expect(screen.getByLabelText('Location')).toHaveValue('Old typed location');
  });
});
