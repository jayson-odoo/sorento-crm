/**

 * PS-REGISTER-CHECK-FIRST AC-W1..W9: the Register form is a two-step wizard in create mode
 * (step strip Check / Details via components/common/WizardSteps.tsx), one flat form in edit mode.
 * Harness copied from ProjectForm.v2.test.tsx (network boundary = apiFetch, stubbed selects).
 * Assumptions: the step strip is WizardSteps' <ol aria-label="Steps"> with aria-current="step";
 * the footer buttons are Back / Cancel / Check|Next|Register as secondary lead on <code>;
 * the clash result lines are "No clash" and "Clash: <code> <title>"; the failure line is
 * "The check did not finish. Try again." (clash-preview answering 500).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { toast } from '@/lib/toast';
import type { Project } from '../types/project.types';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  usePathname: () => '/project-sales/new',
  useRouter: () => ({ push, replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { id: 'u-me', name: 'Sales A' } }, status: 'authenticated' }),
}));

let granted = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => granted.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => granted.has(s)),
  usePermissions: () => ({
    permissions: [...granted],
    permissionSet: granted,
    isLoading: false,
    isError: false,
    isFetching: false,
    refetch: vi.fn(),
  }),
}));

vi.mock('@/services/userSelectService', () => ({
  getUserLookup: vi.fn(async () => [
    { id: 'u-me', name: 'Sales A' },
    { id: 'u-2', name: 'Sales B' },
  ]),
}));
vi.mock('@/app/(protected)/master-data-management/shared/hooks/use-brand-select-query', () => ({
  useBrandSelectQuery: () => ({ data: [{ id: 'b1', brand_name: 'CONTOH Brand' }], isLoading: false }),
}));
vi.mock('@/hooks/useLookupSetOptions', () => ({
  useLookupSetOptions: () => ({
    data: [
      { value: 'Johor', label: 'Johor' },
      { value: 'Selangor', label: 'Selangor' },
    ],
    error: null,
    refetch: vi.fn(),
  }),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), custom: vi.fn() },
}));
vi.mock('@/components/common/AttachmentPreviewModal', () => ({
  __esModule: true,
  default: () => null,
}));

// ---------------------------------------------------------------- network boundary
type Call = { url: string; method: string; body: unknown; form: FormData | null };
const calls: Call[] = [];
let clashAnswer: (body: { developer_party_id?: string | null }) => unknown;
let aiAnswer: unknown;
let clashFail = false;

const PARTIES = [
  { id: 'd1', party_type: 'developer', name: 'SP Setia CONTOH', is_active: true },
  { id: 'd2', party_type: 'developer', name: 'Perdana CONTOH', is_active: true },
  { id: 'a1', party_type: 'architect', name: 'Arkitek CONTOH', is_active: true },
  { id: 'c1', party_type: 'main_contractor', name: 'Bina CONTOH', is_active: true },
];
const CUSTOMERS = [
  { id: 'cust-1', customer_code: 'C-0001', customer_name: 'Aman Hartanah CONTOH' },
  { id: 'cust-2', customer_code: 'C-0002', customer_name: 'Bestari Dealer CONTOH' },
];
const TYPE = {
  id: 'ty2',
  name: 'Hotel',
  code: 'HOTEL',
  derives_delivery_from_launch: false,
  sort_order: 1,
  is_active: true,
};
const LEAD = {
  id: 'lead-1',
  lead_code: 'LEAD-000001',
  title: 'Menara Lead CONTOH',
  outcome: 'open',
  customer_id: 'cust-1',
  customer_name: 'Aman Hartanah CONTOH',
  owner_user_id: 'u-me',
};
const LEAD_NO_CUSTOMER = {
  id: 'lead-2',
  lead_code: 'LEAD-000002',
  title: 'Menara Tanpa Pelanggan CONTOH',
  outcome: 'open',
  customer_id: null,
  customer_name: null,
  owner_user_id: null,
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...actual,
    apiFetch: async (input: string, init: RequestInit = {}) => {
      const method = (init.method ?? 'GET').toUpperCase();
      const isForm = typeof FormData !== 'undefined' && init.body instanceof FormData;
      const call: Call = {
        url: String(input),
        method,
        body: !isForm && typeof init.body === 'string' ? JSON.parse(init.body) : null,
        form: isForm ? (init.body as FormData) : null,
      };
      calls.push(call);
      const url = new URL(call.url, 'http://x');
      const path = url.pathname;
      if (path.endsWith('/customers/select')) {
        const q = (url.searchParams.get('query') ?? '').toLowerCase();
        const data = CUSTOMERS.filter(
          (c) =>
            c.customer_name.toLowerCase().includes(q) || c.customer_code.toLowerCase().includes(q),
        );
        return json({ data, pagination: { total: data.length, page: 1, limit: 20 } });
      }
      if (path.endsWith('/project-sales/parties/') && method === 'GET') {
        const type = url.searchParams.get('party_type');
        const q = (url.searchParams.get('query') ?? '').toLowerCase();
        const data = PARTIES.filter(
          (p) => (!type || p.party_type === type) && p.name.toLowerCase().includes(q),
        );
        return json({ data, pagination: { total: data.length, page: 1, limit: 20 } });
      }
      if (path.endsWith('/project-sales/parties/') && method === 'POST') {
        const b = call.body as { name: string; party_type: string };
        return json({ id: `new-${b.party_type}`, name: b.name, party_type: b.party_type, is_active: true });
      }
      if (path.endsWith('/config/types')) return json({ data: [TYPE] });
      if (path.endsWith('/config/templates')) return json({ data: [] });
      if (path.endsWith('/project-sales/leads')) {
        const q = (url.searchParams.get('query') ?? '').toLowerCase();
        const data = q.includes('tanpa') ? [LEAD_NO_CUSTOMER] : [LEAD];
        return json({ data, pagination: { total: data.length, page: 1, limit: 20 } });
      }
      if (/\/project-sales\/leads\/lead-\d+$/.test(path)) {
        return json(path.endsWith('lead-2') ? LEAD_NO_CUSTOMER : LEAD);
      }
      if (path.endsWith('/projects/clash-preview') && clashFail) return json({ detail: 'boom' }, 500);
      if (path.endsWith('/projects/clash-preview')) {
        return json(clashAnswer(call.body as { developer_party_id?: string | null }));
      }
      if (path.endsWith('/projects/ai-extract')) return json(aiAnswer);
      if (path.endsWith('/takeover-requests') && method === 'POST') {
        return json({ id: 'tr1', kind: 'dispute', status: 'pending' });
      }
      if (path.endsWith('/project-sales/projects/') && method === 'POST') {
        return json({ id: 'new1', project_code: 'PRJ-000099', title: 'x' });
      }
      return json({ data: [], pagination: { total: 0, page: 1, limit: 20 } });
    },
  };
});

// ---------------------------------------------------------------- control stubs
type Option = { value: string; label: string; description?: string };

vi.mock('@/components/common/SearchableSelect', () => {
  function StaticSelect({ id, value, onChange, options, disabled }: never) {
    const o = options as Option[] | undefined;
    return (
      <select
        id={id}
        value={value}
        disabled={disabled}
        onChange={(e) => (onChange as (v: string) => void)(e.target.value)}
      >
        <option value="" />
        {(o ?? []).map((x) => (
          <option key={x.value} value={x.value}>
            {x.label}
          </option>
        ))}
      </select>
    );
  }
  function AsyncSelect(props: {
    id?: string;
    value: string;
    onChange: (v: string) => void;
    onOptionChange?: (o: Option | null) => void;
    fetchOptions: (q: string, page: number) => Promise<Option[]>;
    selectedOption?: Option;
    emptyMessage?: string;
    createOption?: { label: (q: string) => React.ReactNode; onCreate: (q: string) => unknown };
  }) {
    const [query, setQuery] = React.useState('');
    const [results, setResults] = React.useState<Option[] | null>(null);
    const shown =
      query === '' && props.selectedOption && props.selectedOption.value === props.value
        ? props.selectedOption.label
        : query;
    return (
      <span>
        <input
          id={props.id}
          value={shown}
          placeholder="Search"
          onChange={(e) => {
            setQuery(e.target.value);
            void props.fetchOptions(e.target.value, 0).then(setResults);
          }}
        />
        <div data-testid={`results-${props.id}`}>
          {(results ?? []).map((o) => (
            <button
              key={o.value}
              type="button"
              onClick={() => {
                props.onChange(o.value);
                props.onOptionChange?.(o);
                setResults(null);
                setQuery('');
              }}
            >
              {o.label}
              {o.description ? <small>{o.description}</small> : null}
            </button>
          ))}
          {results && results.length === 0 && query && props.emptyMessage ? (
            <p>{props.emptyMessage}</p>
          ) : null}
          {props.createOption && query ? (
            <button
              type="button"
              onClick={async () => {
                await props.createOption!.onCreate(query);
                setQuery('');
                setResults(null);
              }}
            >
              {props.createOption.label(query)}
            </button>
          ) : null}
        </div>
      </span>
    );
  }
  return {
    SearchableSelect: (props: Record<string, unknown>) =>
      props.fetchOptions ? <AsyncSelect {...(props as never)} /> : <StaticSelect {...(props as never)} />,
  };
});
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({ id }: { id?: string }) => <select id={id} multiple />,
}));
vi.mock('@/components/ui/date-range-picker', () => ({
  DateRangePicker: ({ id }: { id?: string }) => <input id={id} />,
}));

import { ProjectForm } from './ProjectForm';

// ---------------------------------------------------------------- helpers
const BLOCKING = {
  project_id: 'p9',
  project_code: 'PRJ-000009',
  title: 'Setia Alam Phase 3B CONTOH',
  outcome: 'open',
  owner_name: 'Manager M',
  similarity: 0.95,
  blocks: true,
};
const SIMILAR = {
  project_id: 'p10',
  project_code: 'PRJ-000010',
  title: 'Setia Alam Phase 3C CONTOH',
  outcome: 'open',
  owner_name: 'Sales B',
  similarity: 0.6,
  blocks: false,
};

function editProject(over: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    project_code: 'PRJ-000001',
    title: 'Menara Lama CONTOH',
    outcome: 'open',
    is_critical: false,
    developer_party_id: 'd1',
    developer_name: 'SP Setia CONTOH',
    type_id: 'ty2',
    owner_user_id: 'u-2',
    brands: ['CONTOH Brand'],
    brand_ids: ['b1'],
    can_edit: true,
    next_action_overdue: false,
    stale_level: 0,
    is_unattended: false,
    open_task_count: 0,
    ...over,
  } as Project;
}

function renderForm(props: { mode: 'create' } | { mode: 'edit'; project: Project } = { mode: 'create' }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ProjectForm {...props} />
    </QueryClientProvider>,
  );
}

const titleBox = () => screen.getByLabelText(/project title/i) as HTMLTextAreaElement;
function typeTitle(text: string) {
  fireEvent.change(titleBox(), { target: { value: text } });
  fireEvent.blur(titleBox());
}
async function pickAsync(label: string | RegExp, typed: string, optionName: string | RegExp) {
  fireEvent.change(screen.getByLabelText(label), { target: { value: typed } });
  fireEvent.click(await screen.findByRole('button', { name: optionName }));
}
// LEAD-GOVERNS-REGISTER D2: a new project's Customer comes from the picked Lead, so "pickCustomer"
// now picks the lead whose customer is Aman Hartanah CONTOH.
const pickCustomer = (typed = 'Menara') => pickAsync(/^Lead/, typed, /Menara Lead CONTOH/);
const pickCustomerlessLead = () =>
  pickAsync(/^Lead/, 'Tanpa', /Menara Tanpa Pelanggan CONTOH/);
function openDetails() {
  const header = screen.getByRole('button', { name: /^Details/ });
  if (header.getAttribute('aria-expanded') !== 'true') fireEvent.click(header);
}
const callsTo = (method: string, part: string) =>
  calls.filter((c) => c.method === method && c.url.includes(part));
const registerBody = () =>
  calls.find((c) => c.method === 'POST' && c.url.split('?')[0].endsWith('/project-sales/projects/'))
    ?.body as Record<string, unknown> | undefined;
/** The deepest element whose whole text is exactly `text` (one visible line). */
function linesWithText(text: string): HTMLElement[] {
  const norm = (s: string | null) => (s ?? '').replace(/\s+/g, ' ').trim();
  const all = Array.from(document.body.querySelectorAll<HTMLElement>('*')).filter(
    (el) => norm(el.textContent) === text,
  );
  return all.filter((el) => !Array.from(el.children).some((c) => all.includes(c as HTMLElement)));
}

beforeEach(() => {
  vi.clearAllMocks();
  calls.length = 0;
  granted = new Set(['projects.projects.edit', 'projects.projects.manage']);
  clashAnswer = () => ({ candidates: [], would_block: false });
  aiAnswer = {};
  clashFail = false;
});


const stepStrip = () => screen.queryByRole('list', { name: 'Steps' });
const currentStep = () => within(stepStrip() as HTMLElement).getByRole('listitem', { current: 'step' });
const developerBox = () => screen.getByLabelText('Developer');

async function runCheck(text = 'Setia Alam Phase 3B CONTOH') {
  typeTitle(text);
  fireEvent.click(screen.getByRole('button', { name: 'Check' }));
  await waitFor(() => expect(callsTo('POST', '/projects/clash-preview').length).toBeGreaterThan(0));
}
async function toDetails() {
  await runCheck();
  fireEvent.click(await screen.findByRole('button', { name: 'Next' }));
  await screen.findByRole('button', { name: /Lead, customer and salesperson/ });
}

describe('AC-W1 create mode opens on step 1 only', () => {
  it('AC-W1 shows the Check / Details step strip with Check current', () => {
    renderForm();
    const strip = stepStrip();
    expect(strip).not.toBeNull();
    expect(within(strip as HTMLElement).getByText('Check')).toBeInTheDocument();
    expect(within(strip as HTMLElement).getByText('Details')).toBeInTheDocument();
    expect(currentStep()).toHaveTextContent('Check');
  });

  it('AC-W1 step 1 holds Project title, AI extract and Developer and none of the later fields', () => {
    renderForm();
    expect(titleBox()).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'AI extract' })).toBeInTheDocument();
    expect(developerBox()).toBeInTheDocument();
    expect(screen.queryByLabelText('Project type')).toBeNull();
    expect(screen.queryByLabelText(/^Lead/)).toBeNull();
    expect(screen.queryByLabelText('Salesperson')).toBeNull();
    expect(screen.queryByRole('button', { name: /Lead, customer and salesperson/ })).toBeNull();
  });

  it.each(['Register project', 'Save draft', 'Submit for approval'])('AC-W1 step 1 has no "%s" button', (name) => {
    granted = new Set(['projects.registrations.submit']);
    renderForm();
    expect(screen.queryByRole('button', { name })).toBeNull();
    cleanup();
    granted = new Set(['projects.projects.edit']);
    renderForm();
    expect(screen.queryByRole('button', { name })).toBeNull();
  });

  it('AC-W1 footer: Back disabled, Cancel and Check present', () => {
    renderForm();
    expect(screen.getByRole('button', { name: 'Back' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Check' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Next' })).toBeNull();
  });
});

describe('AC-W2 / AC-W3 no blocking clash', () => {
  it('AC-W2 an empty result shows "No clash" and the action becomes Next', async () => {
    renderForm();
    await runCheck();
    expect(await screen.findByText('No clash')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: 'Check' })).toBeNull();
  });

  it('AC-W3 only non-blocking rows also show just "No clash" and Next, with no similar rows', async () => {
    clashAnswer = () => ({ candidates: [SIMILAR], would_block: false });
    renderForm();
    await runCheck('Setia Alam Phase 3C CONTOH');
    expect(await screen.findByText('No clash')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next' })).toBeInTheDocument();
    expect(screen.queryByText(/Similar project/)).toBeNull();
    expect(screen.queryByText(/PRJ-000010/)).toBeNull();
  });
});

describe('AC-W4 blocking clash', () => {
  beforeEach(() => {
    clashAnswer = () => ({ candidates: [BLOCKING], would_block: true });
  });

  it('AC-W4 one "Clash: <code> <title>" line and the forward action is Register as secondary lead on <code>', async () => {
    renderForm();
    await runCheck();
    await waitFor(() =>
      expect(linesWithText('Clash: PRJ-000009 Setia Alam Phase 3B CONTOH')).toHaveLength(1),
    );
    expect(screen.getByRole('button', { name: 'Register as secondary lead on PRJ-000009' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: 'Next' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Check' })).toBeNull();
    expect(screen.queryByText('No clash')).toBeNull();
  });
});

describe('AC-W5 the check fails', () => {
  it('AC-W5 shows "The check did not finish. Try again." and the action stays Check', async () => {
    clashFail = true;
    renderForm();
    typeTitle('Setia Alam Phase 3B CONTOH');
    fireEvent.click(screen.getByRole('button', { name: 'Check' }));
    expect(await screen.findByText('The check did not finish. Try again.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Check' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: 'Next' })).toBeNull();
    expect(screen.queryByText('No clash')).toBeNull();
  });
});

describe('AC-W6 editing after a Check clears it', () => {
  it('AC-W6 changing the title brings Check back and removes the result', async () => {
    renderForm();
    await runCheck();
    await screen.findByRole('button', { name: 'Next' });
    typeTitle('Something else entirely CONTOH');
    expect(await screen.findByRole('button', { name: 'Check' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Next' })).toBeNull();
    expect(screen.queryByText('No clash')).toBeNull();
  });

  it('AC-W6 changing the developer after a blocking Check clears the clash line and returns to Check', async () => {
    clashAnswer = () => ({ candidates: [BLOCKING], would_block: true });
    renderForm();
    await runCheck();
    await screen.findByRole('button', { name: 'Register as secondary lead on PRJ-000009' });
    await pickAsync('Developer', 'Perdana', /Perdana CONTOH/);
    expect(await screen.findByRole('button', { name: 'Check' })).toBeInTheDocument();
    expect(screen.queryByText(/^Clash:/)).toBeNull();
    expect(screen.queryByRole('button', { name: /Register as secondary lead on/ })).toBeNull();
  });
});

describe('AC-W7 step 2 Details', () => {
  it('AC-W7 Next shows Details and Lead, customer and salesperson, with the step strip on Details', async () => {
    renderForm();
    await toDetails();
    expect(currentStep()).toHaveTextContent('Details');
    expect(screen.getByRole('button', { name: /^Details/ })).toBeInTheDocument();
    expect(screen.getByLabelText(/^Lead/)).toBeInTheDocument();
    expect(screen.getByLabelText('Salesperson')).toBeInTheDocument();
  });

  it('AC-W7 staff get Register project bottom right, Back enabled, no Check / Next', async () => {
    renderForm();
    await toDetails();
    expect(screen.getByRole('button', { name: 'Register project' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Back' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: 'Next' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Check' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Save draft' })).toBeNull();
  });

  it('AC-W7 a submit-only salesperson gets Save draft and Submit for approval', async () => {
    granted = new Set(['projects.registrations.submit']);
    renderForm();
    await toDetails();
    expect(screen.getByRole('button', { name: 'Save draft' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Submit for approval' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Register project' })).toBeNull();
  });

  it('AC-W7 Register project keeps today\'s rule: disabled until a Lead is picked, then sends title and lead_id', async () => {
    renderForm();
    await toDetails();
    expect(screen.getByRole('button', { name: 'Register project' })).toBeDisabled();
    await pickAsync(/^Lead/, 'Menara', /Menara Lead CONTOH/);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Register project' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Register project' }));
    await waitFor(() => expect(registerBody()).toBeTruthy());
    expect(registerBody()).toMatchObject({ title: 'Setia Alam Phase 3B CONTOH', lead_id: 'lead-1' });
  });

  it('AC-W7 Back returns to step 1 keeping the typed title and developer', async () => {
    renderForm();
    await pickAsync('Developer', 'SP Setia', /SP Setia CONTOH/);
    await toDetails();
    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
    expect(await screen.findByLabelText(/project title/i)).toHaveValue('Setia Alam Phase 3B CONTOH');
    expect(currentStep()).toHaveTextContent('Check');
    expect(developerBox()).toHaveValue('SP Setia CONTOH');
  });

  it('AC-W7 Back keeps values typed on step 2', async () => {
    renderForm();
    await toDetails();
    await pickAsync(/^Lead/, 'Menara', /Menara Lead CONTOH/);
    fireEvent.click(screen.getByRole('button', { name: 'Back' }));
    await screen.findByLabelText(/project title/i);
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(await screen.findByLabelText(/^Lead/)).toHaveValue('Menara Lead CONTOH');
  });
});

describe('AC-W8 AI extract on step 1', () => {
  const PROPOSALS = {
    developer: { status: 'match', id: 'd1', name: 'SP Setia CONTOH' },
    architect: { status: 'match', id: 'a1', name: 'Arkitek CONTOH' },
    state: { status: 'match', name: 'Selangor', value: 'Selangor' },
    mukim: 'Petaling',
  };

  it('AC-W8 fills title and developer on step 1 and keeps the rest for step 2 (sent on register)', async () => {
    aiAnswer = PROPOSALS;
    renderForm();
    typeTitle('Menara Pavilion CONTOH hotel tiga puluh tingkat');
    fireEvent.click(screen.getByRole('button', { name: 'AI extract' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'AI Extract' }));
    await screen.findByTestId('ai-extract-review');
    fireEvent.click(screen.getByRole('button', { name: 'Confirm and prefill' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(currentStep()).toHaveTextContent('Check');
    expect(titleBox().value).toBe('Menara Pavilion CONTOH hotel tiga puluh tingkat');
    await waitFor(() => expect(developerBox()).toHaveValue('SP Setia CONTOH'));
    fireEvent.click(screen.getByRole('button', { name: 'Check' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Next' }));
    await pickAsync(/^Lead/, 'Menara', /Menara Lead CONTOH/);
    fireEvent.click(screen.getByRole('button', { name: 'Register project' }));
    await waitFor(() => expect(registerBody()).toBeTruthy());
    expect(registerBody()).toMatchObject({
      developer_party_id: 'd1',
      architect_party_id: 'a1',
      state: 'Selangor',
      mukim: 'Petaling',
    });
  });
});

describe('AC-W9 edit mode is not a wizard', () => {
  it('AC-W9 no step strip and every section shows at once', () => {
    renderForm({ mode: 'edit', project: editProject() });
    expect(stepStrip()).toBeNull();
    expect(screen.getByRole('button', { name: /^Details/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Lead, customer and salesperson/ })).toBeInTheDocument();
    expect(screen.getByLabelText(/project title/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Next' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Back' })).toBeNull();
  });

  it('AC-W9 Check shows the same No clash result and no similar rows', async () => {
    clashAnswer = () => ({ candidates: [SIMILAR], would_block: false });
    renderForm({ mode: 'edit', project: editProject() });
    fireEvent.click(screen.getByRole('button', { name: 'Check' }));
    expect(await screen.findByText('No clash')).toBeInTheDocument();
    expect(screen.queryByText(/Similar project/)).toBeNull();
    expect(screen.queryByText(/PRJ-000010/)).toBeNull();
  });

  it('AC-W9 Check on a clashing rename shows "Clash: <code> <title>"', async () => {
    clashAnswer = () => ({ candidates: [BLOCKING], would_block: true });
    renderForm({ mode: 'edit', project: editProject() });
    typeTitle('Setia Alam Phase 3B CONTOH');
    fireEvent.click(screen.getByRole('button', { name: 'Check' }));
    await waitFor(() =>
      expect(linesWithText('Clash: PRJ-000009 Setia Alam Phase 3B CONTOH')).toHaveLength(1),
    );
  });
});

describe('AC-W10 footer stacks like Create lead', () => {
  // Create lead (LeadWizardDialog) stacks Back, Cancel, forward in DOM order with a plain
  // flex-col; a flex-col-reverse on the Cancel / forward group would flip them at 375px.
  const footerOrder = () => {
    const names = ['Back', 'Cancel'];
    const back = screen.getByRole('button', { name: 'Back' });
    const cancel = screen.getByRole('button', { name: 'Cancel' });
    const row = back.parentElement as HTMLElement;
    const buttons = Array.from(row.querySelectorAll('button'));
    return { names, back, cancel, buttons, group: cancel.parentElement as HTMLElement };
  };

  it('AC-W10 step 1 footer order is Back, Cancel, Check, and the group does not reverse', () => {
    renderForm();
    const { buttons, group } = footerOrder();
    expect(buttons.map((b) => (b.textContent ?? '').trim())).toEqual(['Back', 'Cancel', 'Check']);
    expect(group.className).not.toMatch(/flex-col-reverse/);
  });

  it('AC-W10 step 2 footer order is Back, Cancel, Register project', async () => {
    renderForm();
    await toDetails();
    const { buttons, group } = footerOrder();
    expect(buttons.map((b) => (b.textContent ?? '').trim())).toEqual(['Back', 'Cancel', 'Register project']);
    expect(group.className).not.toMatch(/flex-col-reverse/);
  });
});

describe('AC-W4 a clash found at submit time on step 2', () => {
  it('AC-W4 shows the "Clash: <code> <title>" line together with Register as secondary lead on <code>', async () => {
    let n = 0;
    clashAnswer = () => (++n === 1 ? { candidates: [], would_block: false } : { candidates: [BLOCKING], would_block: true });
    renderForm();
    await toDetails();
    await pickAsync(/^Lead/, 'Menara', /Menara Lead CONTOH/);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Register project' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Register project' }));
    expect(
      await screen.findByRole('button', { name: 'Register as secondary lead on PRJ-000009' }),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(linesWithText('Clash: PRJ-000009 Setia Alam Phase 3B CONTOH')).toHaveLength(1),
    );
    // Still on step 2, and nothing was registered.
    expect(screen.getByLabelText(/^Lead/)).toBeInTheDocument();
    expect(registerBody()).toBeUndefined();
  });
});
