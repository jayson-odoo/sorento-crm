/**
 * PROJECT-REGISTER-V2, Phase 2 red tests for the Register / Edit form
 * (UAC project-register-v2-acceptance-criteria.md: A1-A4, B1-B3, C1, C7, C8, D2-D4, D7, G3, J1).
 *
 * Written from the UAC and the approved mock v1.4, before any implementation. Everything the
 * form sends is observed at the network boundary (`apiFetch` from `@/lib/api`), so the tests do
 * not care what the new hooks and services are called, only which `/api/v1/*` call fires and
 * with what.
 *
 * Assumed contract shapes (stated so a mismatch is visible to the coder, not hidden):
 * - Searchable fields use `SearchableSelect`'s existing async mode (`fetchOptions`,
 *   `createOption`, `emptyMessage`), the way the Lead field does today. The stub below
 *   implements that mode.
 * - `POST /api/v1/project-sales/projects/ai-extract` answers a top-level object with one
 *   proposal per field (UAC C3): `{ developer: {status, id, name}, architect: {...}, ... }`;
 *   `state` is {status, name, value}; `title` and `mukim` arrive as PLAIN STRINGS, as the real
 *   backend sends them (UAC C6).
 * - The register body carries `customer_id` (UAC A5).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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
});

// ---------------------------------------------------------------- A
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
  await screen.findByRole('button', { name: /Lead, customer and salesperson/ });
}

describe('A1 title first, as a textarea', () => {
  it('the title is a textarea and the first control of Who and what', () => {
    const { container } = renderForm();
    expect(titleBox().tagName).toBe('TEXTAREA');
    expect(container.querySelector('input, textarea, select')).toBe(titleBox());
  });

  it('Developer, Project type and Template follow the title', async () => {
    renderForm();
    const developer = screen.getByLabelText('Developer');
    const follows = (el: Element) =>
      Boolean(titleBox().compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING);
    expect(follows(developer)).toBe(true);
    // Project type sits on the Details step now, after the Check step that holds the title.
    await toDetails();
    expect(screen.getByLabelText('Project type')).toBeInTheDocument();
  });
});

describe('A2 Lead, customer and salesperson', () => {
  it('names the section Lead, customer and salesperson and holds Lead and Salesperson', async () => {
    renderForm();
    await toDetails();
    expect(screen.queryByRole('button', { name: /^Salesperson and customer/ })).toBeNull();
    const header = screen.getByRole('button', { name: /Lead, customer and salesperson/ });
    const section = header.closest('[data-slot="card"]') as HTMLElement;
    expect(within(section).getByLabelText('Salesperson')).toBeInTheDocument();
    expect(within(section).getByLabelText(/^Lead/)).toBeInTheDocument();
  });

  it('Lead sits in the bottom section, not Details, and keeps its create row', async () => {
    renderForm();
    await toDetails();
    openDetails();
    const details = screen.getByRole('button', { name: /^Details/ }).closest('[data-slot="card"]') as HTMLElement;
    expect(within(details).queryByLabelText(/^Lead/)).toBeNull();
    const lead = screen.getByLabelText(/^Lead/);
    fireEvent.change(lead, { target: { value: 'Pavilion' } });
    expect(await screen.findByRole('button', { name: /Create lead/ })).toBeInTheDocument();
  });
});

describe('A3 Customer is an async search over the customers select', () => {
  it('a lead with no customer: searches GET /api/v1/order-management/customers/select with the typed query', async () => {
    renderForm();
    await toDetails();
    await pickCustomerlessLead();
    fireEvent.change(screen.getByLabelText(/^Customer/), { target: { value: 'Aman' } });
    await screen.findByRole('button', { name: /Aman Hartanah CONTOH/ });
    const get = callsTo('GET', '/api/v1/order-management/customers/select').pop();
    expect(get).toBeTruthy();
    expect(new URL(get!.url, 'http://x').searchParams.get('query')).toBe('Aman');
  });

  it('options show the customer name only, never the debtor code', async () => {
    renderForm();
    await toDetails();
    await pickCustomerlessLead();
    fireEvent.change(screen.getByLabelText(/^Customer/), { target: { value: 'CONTOH' } });
    await screen.findByRole('button', { name: /Bestari Dealer CONTOH/ });
    expect(document.body.textContent).not.toMatch(/C-000\d/);
  });

  it('offers no create row and says "No customers found" on an empty result', async () => {
    renderForm();
    await toDetails();
    await pickCustomerlessLead();
    fireEvent.change(screen.getByLabelText(/^Customer/), { target: { value: 'zzzz' } });
    expect(await screen.findByText('No customers found')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /create customer/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /^Create /i })).toBeNull();
  });
});

describe('A4 Register needs title and a Lead (its customer comes with it)', () => {
  it('create: disabled with a title only, enabled once a Lead is picked, sends lead_id', async () => {
    renderForm();
    await toDetails('Menara Baru CONTOH');
    const register = screen.getByRole('button', { name: 'Register project' });
    expect(register).toBeDisabled();
    expect(register).toBeDisabled();
    await pickCustomer();
    await waitFor(() => expect(register).toBeEnabled());
    fireEvent.click(register);
    await waitFor(() => expect(registerBody()).toBeTruthy());
    expect(registerBody()).toMatchObject({ title: 'Menara Baru CONTOH', lead_id: 'lead-1' });
    await waitFor(() => expect(push).toHaveBeenCalledWith('/project-sales/new1'));
  });

  it('edit: Lead is optional, Save changes is enabled without one', () => {
    renderForm({ mode: 'edit', project: editProject() });
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeEnabled();
  });
});

// ---------------------------------------------------------------- B
describe('B1 Developer, Architect, Main contractor search the parties endpoint', () => {
  it.each([
    ['Developer', 'developer', 'Setia'],
    ['Architect', 'architect', 'Arkitek'],
    ['Main contractor', 'main_contractor', 'Bina'],
  ])('%s searches by party_type and query, not a fixed limit-200 list', async (label, type, typed) => {
    renderForm();
    // Developer sits on the Check step; Architect and Main contractor on Details.
    if (label !== 'Developer') {
      await toDetails();
      openDetails();
    }
    fireEvent.change(screen.getByLabelText(label), { target: { value: typed } });
    await waitFor(() => {
      const hit = callsTo('GET', '/project-sales/parties/').find((c) => {
        const sp = new URL(c.url, 'http://x').searchParams;
        return sp.get('party_type') === type && sp.get('query') === typed;
      });
      expect(hit).toBeTruthy();
    });
    expect(callsTo('GET', '/project-sales/parties/').some((c) => c.url.includes('limit=200'))).toBe(false);
  });
});

describe('B2 / B3 create a party on the spot', () => {
  it.each([
    ['Developer', 'developer', 'Create developer'],
    ['Architect', 'architect', 'Create architect'],
    ['Main contractor', 'main_contractor', 'Create main contractor'],
  ])('with projects.parties.edit, %s offers a create row that POSTs and selects', async (label, type, rowText) => {
    granted.add('projects.parties.edit');
    renderForm();
    if (label !== 'Developer') {
      await toDetails('Menara Pilih CONTOH');
      openDetails();
    }
    fireEvent.change(screen.getByLabelText(label), { target: { value: 'Kelana Baru' } });
    fireEvent.click(await screen.findByRole('button', { name: new RegExp(`${rowText} .*Kelana Baru`, 'i') }));
    await waitFor(() => expect(callsTo('POST', '/project-sales/parties/')).toHaveLength(1));
    expect(callsTo('POST', '/project-sales/parties/')[0].body).toEqual({
      name: 'Kelana Baru',
      party_type: type,
    });

    if (label === 'Developer') {
      typeTitle('Menara Pilih CONTOH');
      await toDetails();
    }
    await pickCustomer();
    const key = { developer: 'developer_party_id', architect: 'architect_party_id', main_contractor: 'main_contractor_party_id' }[type]!;
    fireEvent.click(screen.getByRole('button', { name: 'Register project' }));
    await waitFor(() => expect(registerBody()).toBeTruthy());
    expect(registerBody()![key]).toBe(`new-${type}`);
  });

  it.each(['Developer', 'Architect', 'Main contractor'])(
    'without projects.parties.edit, %s has no create row',
    async (label) => {
      renderForm();
      if (label !== 'Developer') {
        await toDetails();
        openDetails();
      }
      fireEvent.change(screen.getByLabelText(label), { target: { value: 'Kelana Baru' } });
      await waitFor(() => expect(callsTo('GET', '/project-sales/parties/').length).toBeGreaterThan(0));
      expect(screen.queryByRole('button', { name: /^Create (developer|architect|main contractor)/i })).toBeNull();
    },
  );
});

// ---------------------------------------------------------------- C1
describe('C1 Check and AI extract sit side by side under the title', () => {
  it('both buttons share one row, after the title; no separate Add photo button', async () => {
    // Create mode keeps Check in the wizard footer; the shared row is the edit form's.
    renderForm({ mode: 'edit', project: editProject() });
    const check = screen.getByRole('button', { name: 'Check' });
    const ai = screen.getByRole('button', { name: 'AI extract' });
    expect(check.parentElement).toBe(ai.parentElement);
    expect(titleBox().compareDocumentPosition(check) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByRole('button', { name: /add photo/i })).toBeNull();
  });
});

// ---------------------------------------------------------------- D
async function checkTitle(text = 'Setia Alam Phase 3B CONTOH') {
  typeTitle(text);
  fireEvent.click(screen.getByRole('button', { name: 'Check' }));
  await waitFor(() => expect(callsTo('POST', '/projects/clash-preview').length).toBeGreaterThan(0));
}

describe('D2 a blocking clash becomes Register interest', () => {
  beforeEach(() => {
    clashAnswer = () => ({ candidates: [BLOCKING], would_block: true });
  });

  it('AC-W4 shows ONE line "Clash: <code> <title>" with the code linking to the project', async () => {
    renderForm();
    await checkTitle();
    const line = await waitFor(() => {
      const found = linesWithText('Clash: PRJ-000009 Setia Alam Phase 3B CONTOH');
      expect(found).toHaveLength(1);
      return found[0];
    });
    expect(within(line).getByRole('link', { name: 'PRJ-000009' })).toHaveAttribute('href', '/project-sales/p9');
    expect(within(line).queryByRole('button')).toBeNull();
    expect(screen.queryByText(/Manager M/)).toBeNull();
    expect(screen.queryByText(/Stage:|Owner:|%/)).toBeNull();
    expect(screen.queryByRole('button', { name: /Ask to join|Dispute/ })).toBeNull();
    expect(screen.queryByText(/Blocked by an existing project/)).toBeNull();
  });

  it('AC-R2 the one primary reads "Register as secondary lead on <code>", enabled, with Cancel kept', async () => {
    renderForm();
    await checkTitle();
    const primary = await screen.findByRole('button', { name: 'Register as secondary lead on PRJ-000009' });
    expect(primary).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Register project' })).toBeNull();
    expect(screen.queryByText(/Dispute/)).toBeNull();
  });

  it('AC-R2 D4 the primary opens a dialog that needs a note, posts kind dispute and goes to the project', async () => {
    renderForm();
    await checkTitle();
    fireEvent.click(await screen.findByRole('button', { name: 'Register as secondary lead on PRJ-000009' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Register as secondary lead on PRJ-000009')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Register as secondary lead' })).toBeInTheDocument();
    expect(screen.queryByText(/register interest/i)).toBeNull();
    const note = within(dialog).getByLabelText(/How and when did you find this project\?/);
    expect(note.tagName).toBe('TEXTAREA');
    fireEvent.submit(note.closest('form') as HTMLFormElement);
    expect(callsTo('POST', '/takeover-requests')).toHaveLength(0);
    fireEvent.change(note, { target: { value: 'Met the developer in March with notes.' } });
    fireEvent.submit(note.closest('form') as HTMLFormElement);
    await waitFor(() => expect(callsTo('POST', '/projects/p9/takeover-requests')).toHaveLength(1));
    expect(callsTo('POST', '/projects/p9/takeover-requests')[0].body).toEqual({
      kind: 'dispute',
      reason: 'Met the developer in March with notes.',
    });
    await waitFor(() => expect(push).toHaveBeenCalledWith('/project-sales/p9'));
    expect(registerBody()).toBeUndefined();
  });

  it('D7 naming a different developer clears the match and the button returns to Register project', async () => {
    clashAnswer = (b) =>
      b.developer_party_id === 'd2'
        ? { candidates: [], would_block: false }
        : { candidates: [BLOCKING], would_block: true };
    renderForm();
    await checkTitle();
    await screen.findByRole('button', { name: 'Register as secondary lead on PRJ-000009' });
    await pickAsync('Developer', 'Perdana', /Perdana CONTOH/);
    await toDetails(); // the result was cleared; Check again, then Next
    expect(await screen.findByRole('button', { name: 'Register project' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Register as secondary lead on/ })).toBeNull();
  });
});

describe('D3 a non-blocking candidate is shown as No clash (AC-W3)', () => {
  it('AC-W3 a non-blocking candidate shows just "No clash": no similar row, no action', async () => {
    clashAnswer = () => ({ candidates: [SIMILAR], would_block: false });
    renderForm();
    await checkTitle('Setia Alam Phase 3C CONTOH');
    expect(await screen.findByText('No clash')).toBeInTheDocument();
    expect(screen.queryByText(/Similar project/)).toBeNull();
    expect(screen.queryByText(/PRJ-000010/)).toBeNull();
    expect(screen.getByRole('button', { name: 'Next' })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------- G3
describe('G3 no Brands field', () => {
  it.each(['create', 'edit'] as const)('%s mode has no Brands control', async (mode) => {
    if (mode === 'create') {
      renderForm();
      await toDetails();
    } else renderForm({ mode: 'edit', project: editProject() });
    openDetails();
    expect(screen.queryByLabelText(/brands/i)).toBeNull();
    expect(screen.queryByText(/^Brands$/)).toBeNull();
    expect(screen.queryByText('CONTOH Brand')).toBeNull();
  });

  it('the register body carries no brand_ids', async () => {
    renderForm();
    await toDetails('Menara Tanpa Jenama CONTOH');
    await pickCustomer();
    fireEvent.click(screen.getByRole('button', { name: 'Register project' }));
    await waitFor(() => expect(registerBody()).toBeTruthy());
    expect(registerBody()).not.toHaveProperty('brand_ids');
  });
});

// ---------------------------------------------------------------- J1
describe('J1 salesperson footer', () => {
  it('submit-only user: Cancel, Save draft and Submit for approval; no Register project', async () => {
    granted = new Set(['projects.registrations.submit']);
    renderForm();
    await toDetails();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save draft' })).toBeInTheDocument();
    const primary = screen.getByRole('button', { name: 'Submit for approval' });
    expect(primary).toHaveAttribute('type', 'submit');
    expect(screen.queryByRole('button', { name: 'Register project' })).toBeNull();
  });

  it('submit-only user: Save draft needs only a title; Submit for approval also needs a Lead', async () => {
    granted = new Set(['projects.registrations.submit']);
    renderForm();
    await toDetails('Draf Menara CONTOH');
    expect(screen.getByRole('button', { name: 'Save draft' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Submit for approval' })).toBeDisabled();
    await pickCustomer();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Submit for approval' })).toBeEnabled());
  });

  it.each([
    ['edit only', ['projects.projects.edit']],
    ['edit and submit', ['projects.projects.edit', 'projects.registrations.submit']],
  ])('staff with %s sees Register project only', async (_n, slugs) => {
    granted = new Set(slugs);
    renderForm();
    await toDetails();
    expect(screen.getByRole('button', { name: 'Register project' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Save draft' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Submit for approval' })).toBeNull();
  });
});

// ---------------------------------------------------------------- AI extract (C1, C7, C8)
describe('AI extract from the form', () => {
  const TITLE = 'Menara Pavilion CONTOH hotel tiga puluh tingkat';
  const PROPOSALS = {
    developer: { status: 'match', id: 'd1', name: 'SP Setia CONTOH' },
    architect: { status: 'new', name: 'Arkitek Baru CONTOH' },
    main_contractor: { status: 'new', name: 'Kontraktor Baru CONTOH' },
    project_type: { status: 'not_found' },
    state: { status: 'match', name: 'Selangor', value: 'Selangor' },
    mukim: 'Petaling',
    customer: { status: 'match', id: 'cust-2', name: 'Bestari Dealer CONTOH' },
    title: 'Tajuk Lain CONTOH',
  };

  async function openDialog(withTitle = true) {
    if (withTitle) typeTitle(TITLE);
    fireEvent.click(screen.getByRole('button', { name: 'AI extract' }));
    return screen.findByRole('dialog');
  }
  async function runExtract(dialog: HTMLElement) {
    fireEvent.click(within(dialog).getByRole('button', { name: 'AI Extract' }));
    return screen.findByTestId('ai-extract-review');
  }

  beforeEach(() => {
    aiAnswer = PROPOSALS;
  });

  it('C1 upload stage reads from the title: checked, read-only, no re-pasting', async () => {
    renderForm();
    const dialog = await openDialog();
    expect(within(dialog).getByText(/Read from/)).toBeInTheDocument();
    const source = within(dialog).getByRole('checkbox', { name: /Project title/ });
    expect(source).toBeChecked();
    expect(within(dialog).getByText(TITLE)).toBeInTheDocument();
    expect(within(dialog).queryByDisplayValue(TITLE)).toBeNull();
    expect(within(dialog).getByRole('button', { name: 'AI Extract' })).toBeEnabled();
  });

  it('C1 AI Extract is disabled when the title source is unchecked and there is no photo', async () => {
    renderForm();
    const dialog = await openDialog();
    fireEvent.click(within(dialog).getByRole('checkbox', { name: /Project title/ }));
    expect(within(dialog).getByRole('button', { name: 'AI Extract' })).toBeDisabled();
  });

  it('C1 with an empty title there is nothing to read and AI Extract is disabled', async () => {
    renderForm();
    const dialog = await openDialog(false);
    expect(within(dialog).getByRole('button', { name: 'AI Extract' })).toBeDisabled();
  });

  it('C2 posts the title as multipart text to the staff ai-extract route', async () => {
    renderForm();
    const dialog = await openDialog();
    await runExtract(dialog);
    const post = callsTo('POST', '/api/v1/project-sales/projects/ai-extract');
    expect(post).toHaveLength(1);
    expect(post[0].form?.get('text')).toBe(TITLE);
  });

  it('C7 lists only match and new proposals with a pill per field; not-found and Customer are absent (LGR-D6)', async () => {
    renderForm();
    const dialog = await openDialog();
    const review = await runExtract(dialog);
    const rowOf = (label: string) => within(review).getByText(label).closest('tr') as HTMLElement;
    expect(within(rowOf('Developer')).getByText('Match')).toBeInTheDocument();
    expect(within(rowOf('Architect')).getByText('New')).toBeInTheDocument();
    expect(within(rowOf('Main contractor')).getByText('New')).toBeInTheDocument();
    expect(within(review).queryByText('Customer')).toBeNull();
    expect(within(review).queryByText('Project type')).toBeNull();
    expect(within(rowOf('Architect')).getByRole('button', { name: /drop|remove/i })).toBeInTheDocument();
  });

  it('C8 Confirm creates New parties first, then fills the form; the typed title is never overwritten', async () => {
    granted.add('projects.parties.edit');
    renderForm();
    const dialog = await openDialog();
    await runExtract(dialog);
    fireEvent.click(screen.getByRole('button', { name: 'Confirm and prefill' }));
    await waitFor(() => expect(callsTo('POST', '/project-sales/parties/')).toHaveLength(2));
    expect(callsTo('POST', '/project-sales/parties/').map((c) => c.body)).toEqual(
      expect.arrayContaining([
        { name: 'Arkitek Baru CONTOH', party_type: 'architect' },
        { name: 'Kontraktor Baru CONTOH', party_type: 'main_contractor' },
      ]),
    );
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(titleBox().value).toBe(TITLE);
    await toDetails();
    // LGR-D6: the extract never sets Customer; Register waits for a Lead.
    expect(screen.getByRole('button', { name: 'Register project' })).toBeDisabled();
    expect(screen.queryByText('Bestari Dealer CONTOH')).toBeNull();
    await pickCustomer();
    fireEvent.click(screen.getByRole('button', { name: 'Register project' }));
    await waitFor(() => expect(registerBody()).toBeTruthy());
    expect(registerBody()).toMatchObject({
      title: TITLE,
      developer_party_id: 'd1',
      architect_party_id: 'new-architect',
      main_contractor_party_id: 'new-main_contractor',
      lead_id: 'lead-1',
      state: 'Selangor',
      mukim: 'Petaling',
    });
    expect(calls.some((c) => c.method === 'POST' && c.url.includes('/customers'))).toBe(false);
  });

  it('C8 without projects.parties.edit the New party rows are skipped and left blank', async () => {
    renderForm();
    const dialog = await openDialog();
    await runExtract(dialog);
    fireEvent.click(screen.getByRole('button', { name: 'Confirm and prefill' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    await toDetails();
    expect(callsTo('POST', '/project-sales/parties/')).toHaveLength(0);
    await pickCustomer();
    fireEvent.click(screen.getByRole('button', { name: 'Register project' }));
    await waitFor(() => expect(registerBody()).toBeTruthy());
    expect(registerBody()!.developer_party_id).toBe('d1');
    expect(registerBody()!.architect_party_id ?? null).toBeNull();
    expect(registerBody()!.main_contractor_party_id ?? null).toBeNull();
  });

  it('C7 removing a row with the x keeps it out of Confirm', async () => {
    granted.add('projects.parties.edit');
    renderForm();
    const dialog = await openDialog();
    const review = await runExtract(dialog);
    const row = within(review).getByText('Architect').closest('tr') as HTMLElement;
    fireEvent.click(within(row).getByRole('button', { name: /drop|remove/i }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm and prefill' }));
    await waitFor(() => expect(callsTo('POST', '/project-sales/parties/')).toHaveLength(1));
    expect(callsTo('POST', '/project-sales/parties/')[0].body).toEqual({
      name: 'Kontraktor Baru CONTOH',
      party_type: 'main_contractor',
    });
  });
});

describe('AI extract with the real backend shape (C6)', () => {
  const PLAIN = {
    developer: { status: 'match', id: 'd1', name: 'SP Setia CONTOH' },
    state: { status: 'match', name: 'Selangor', value: 'Selangor' },
    mukim: 'Batu',
    title: 'Tajuk Dari Gambar CONTOH',
  };

  it('lists the plain-string mukim and fills it', async () => {
    aiAnswer = PLAIN;
    renderForm();
    typeTitle('Menara Ada Tajuk CONTOH');
    fireEvent.click(screen.getByRole('button', { name: 'AI extract' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'AI Extract' }));
    const review = await screen.findByTestId('ai-extract-review');
    // QUOTE-UI-POLISH: Mukim is labelled Area everywhere (owner, 29 Oct).
    expect(within(review).queryByText('Mukim')).toBeNull();
    const row = within(review).getByText('Area').closest('tr') as HTMLElement;
    expect(within(row).getByText('Batu')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm and prefill' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    await toDetails();
    await pickCustomer();
    fireEvent.click(screen.getByRole('button', { name: 'Register project' }));
    await waitFor(() => expect(registerBody()).toBeTruthy());
    expect(registerBody()).toMatchObject({ mukim: 'Batu', title: 'Menara Ada Tajuk CONTOH' });
  });

  it('a photo-only extract fills an EMPTY title from the plain-string title', async () => {
    aiAnswer = PLAIN;
    renderForm();
    fireEvent.click(screen.getByRole('button', { name: 'AI extract' }));
    const dialog = await screen.findByRole('dialog');
    const file = new File(['x'], 'papan.png', { type: 'image/png' });
    fireEvent.change(within(dialog).getByTestId('ai-extract-file-input'), { target: { files: [file] } });
    fireEvent.click(await within(dialog).findByRole('button', { name: 'AI Extract' }));
    await screen.findByTestId('ai-extract-review');
    fireEvent.click(screen.getByRole('button', { name: 'Confirm and prefill' }));
    await waitFor(() => expect(titleBox().value).toBe('Tajuk Dari Gambar CONTOH'));
  });
});

describe('D8 a submit-only salesperson registers interest', () => {
  beforeEach(() => {
    granted = new Set(['projects.projects.view_own', 'projects.registrations.submit']);
    clashAnswer = () => ({
      candidates: [{ project_id: 'p9', project_code: 'PRJ-000009', title: 'Setia Alam Phase 3B CONTOH', blocks: true }],
      would_block: true,
    });
  });

  it('Check still runs and the blocking line shows code and title', async () => {
    renderForm();
    await checkTitle();
    await waitFor(() =>
      expect(linesWithText('Clash: PRJ-000009 Setia Alam Phase 3B CONTOH')).toHaveLength(1),
    );
  });

  it('AC-R2 after Register as secondary lead the user lands on the Projects list with a toast, not on the project', async () => {
    renderForm();
    await checkTitle();
    fireEvent.click(await screen.findByRole('button', { name: 'Register as secondary lead on PRJ-000009' }));
    const dialog = await screen.findByRole('dialog');
    const note = within(dialog).getByLabelText(/How and when did you find this project\?/);
    fireEvent.change(note, { target: { value: 'Met the developer in March.' } });
    fireEvent.submit(note.closest('form') as HTMLFormElement);
    await waitFor(() => expect(callsTo('POST', '/projects/p9/takeover-requests')).toHaveLength(1));
    await waitFor(() => expect(push).toHaveBeenCalledWith('/project-sales/pipeline'));
    expect(push).not.toHaveBeenCalledWith('/project-sales/p9');
    expect(toast.success).toHaveBeenCalledWith('Registered as secondary lead on PRJ-000009');
  });
});

describe('J3c a submit-only user now has the Lead field (LGR-D8)', () => {
  it('shows the Lead control in the bottom section', async () => {
    granted = new Set(['projects.projects.view_own', 'projects.registrations.submit']);
    renderForm();
    await toDetails();
    expect(screen.getByLabelText(/^Lead/)).toBeInTheDocument();
  });
});

describe('edit mode Customer prefilled from a linked lead (round 3)', () => {
  const linked = () =>
    editProject({ customer_id: 'cust-1', customer_name: 'Aman Hartanah CONTOH' } as Partial<Project>);
  const putBody = () => calls.find((c) => c.method === 'PUT')?.body as Record<string, unknown> | undefined;

  it('saves without touching Customer: the PUT body has no customer_id key', async () => {
    renderForm({ mode: 'edit', project: linked() });
    expect(screen.getByLabelText('Customer')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(putBody()).toBeTruthy());
    expect(putBody()).not.toHaveProperty('customer_id');
  });

  it('picking another customer sends the new customer_id', async () => {
    renderForm({ mode: 'edit', project: linked() });
    await pickAsync(/^Customer/, 'Bestari', /Bestari Dealer CONTOH/);
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(putBody()).toBeTruthy());
    expect(putBody()).toMatchObject({ customer_id: 'cust-2' });
  });
});
