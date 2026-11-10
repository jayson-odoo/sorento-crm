/**
 * PROJECT-NAME (owner 10 Nov, card documentation/plans/projects/CARD-project-name-10nov.md):
 * page 1 stays title + developer; the short name is the first field of page 2 "Who and what",
 * prefilled by the AI extract (never over a typed name) and sent as `name`; in edit mode it sits
 * directly under the title. Harness copied from ProjectForm.wizard.test.tsx.
 *
 * Original harness notes: PS-REGISTER-CHECK-FIRST AC-W1..W9: the Register form is a two-step wizard in create mode
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
  // PS-REGISTRATION-V3: the lead source list is its own lookup set.
  useLookupSetOptions: (key: string) => ({
    data: key === 'project_lead_source' ? [{ value: 'site_visit', label: 'Site visit' }] : [
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
// PS-REGISTRATION-V3: Register / Submit need a lead source and the customer is optional, so
// every register flow picks the lead source here, beside the customer.
const pickCustomer = async (typed = 'Aman') => {
  fireEvent.change(screen.getByLabelText(/^Lead source/), { target: { value: 'site_visit' } });
  await pickAsync(/^Customer/, typed, /Aman Hartanah CONTOH/);
};
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
  await screen.findByRole('button', { name: /^Lead source, customer and salesperson/ });
}


const nameBox = () => screen.getByLabelText('Project name') as HTMLInputElement;

describe('PROJECT-NAME page 1 stays lean', () => {
  it('step 1 has no Project name field', () => {
    renderForm();
    expect(titleBox()).toBeInTheDocument();
    expect(screen.queryByLabelText('Project name')).toBeNull();
  });
});

describe('PROJECT-NAME page 2', () => {
  it('Who and what opens with Project name, before Project type', async () => {
    renderForm();
    await toDetails();
    const name = nameBox();
    const type = screen.getByLabelText('Project type');
    expect(name.compareDocumentPosition(type) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(name).toHaveAttribute('maxLength', '80');
  });

  it('a typed name is sent trimmed on register', async () => {
    renderForm();
    await toDetails();
    fireEvent.change(nameBox(), { target: { value: '  Residensi Contoh Phase 2 ' } });
    await pickCustomer();
    fireEvent.click(screen.getByRole('button', { name: 'Register project' }));
    await waitFor(() => expect(registerBody()).toBeTruthy());
    expect(registerBody()).toMatchObject({ name: 'Residensi Contoh Phase 2' });
  });

  it('no name sends null', async () => {
    renderForm();
    await toDetails();
    await pickCustomer();
    fireEvent.click(screen.getByRole('button', { name: 'Register project' }));
    await waitFor(() => expect(registerBody()).toBeTruthy());
    expect(registerBody()).toMatchObject({ name: null });
  });
});

describe('PROJECT-NAME AI extract', () => {
  async function runExtract() {
    fireEvent.click(screen.getByRole('button', { name: 'AI extract' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'AI Extract' }));
    await screen.findByTestId('ai-extract-review');
    fireEvent.click(screen.getByRole('button', { name: 'Confirm and prefill' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  }

  it('the review lists Project name and the confirmed name lands on page 2', async () => {
    aiAnswer = { name: '54 Teres 2 Tingkat, Permatang Badak Perdana' };
    renderForm();
    typeTitle('CADANGAN MEMBINA 54 UNIT RUMAH TERES DUA TINGKAT');
    fireEvent.click(screen.getByRole('button', { name: 'AI extract' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'AI Extract' }));
    const review = await screen.findByTestId('ai-extract-review');
    expect(within(review).getByText('Project name')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm and prefill' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    fireEvent.click(screen.getByRole('button', { name: 'Check' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Next' }));
    expect(await screen.findByLabelText('Project name')).toHaveValue(
      '54 Teres 2 Tingkat, Permatang Badak Perdana',
    );
  });

  it('a typed name is never overwritten by the extract', async () => {
    aiAnswer = { name: 'From the AI' };
    renderForm({ mode: 'edit', project: editProject({ name: 'Typed by hand' }) });
    await runExtract();
    expect(nameBox()).toHaveValue('Typed by hand');
  });
});

describe('PROJECT-NAME edit mode', () => {
  it('Project name sits directly under the title and starts with the stored name', () => {
    renderForm({ mode: 'edit', project: editProject({ name: 'Menara Ringkas' }) });
    const title = titleBox();
    const name = nameBox();
    const developer = developerBox();
    expect(name).toHaveValue('Menara Ringkas');
    expect(title.compareDocumentPosition(name) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(name.compareDocumentPosition(developer) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('the folded section summary shows the name, not the title', () => {
    renderForm({ mode: 'edit', project: editProject({ name: 'Menara Ringkas' }) });
    const header = screen.getByRole('button', { name: /^Who and what/ });
    if (header.getAttribute('aria-expanded') === 'true') fireEvent.click(header);
    const folded = screen.getByRole('button', { name: /^Who and what/ });
    expect(folded).toHaveTextContent('Menara Ringkas');
    expect(folded).not.toHaveTextContent('Menara Lama CONTOH');
  });
});
