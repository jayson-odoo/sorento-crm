/**
 * PORTAL-P4-REQUESTS owner ruling a54382059 (29 Oct): the submit-only narrowing in the form
 * (Save draft / Submit for approval footer, submit after save) applies only to a new
 * registration or an UNAPPROVED one. Editing an approved project (approval_state null or
 * 'approved') is the plain edit form: Save changes, one PUT, no /submit call.
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
const LEAD = { id: 'lead-1', lead_code: 'LEAD-000001', title: 'Menara Lead CONTOH', outcome: 'open' };

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
        return json({ data: [LEAD], pagination: { total: 1, page: 1, limit: 20 } });
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
const pickCustomer = (typed = 'Aman') => pickAsync('Customer *', typed, /Aman Hartanah CONTOH/);
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


const SUBMIT_ONLY = ['projects.registrations.submit', 'projects.projects.view_own'];

describe.each([
  ['staff project (approval_state null)', null],
  ['approved registration', 'approved'],
])('submit-only owner editing a %s', (_name, state) => {
  beforeEach(() => {
    granted = new Set(SUBMIT_ONLY);
  });

  it('shows Save changes, not Save draft or Submit for approval', () => {
    renderForm({ mode: 'edit', project: editProject({ approval_state: state, owner_user_id: 'u-me' } as never) });
    expect(screen.getByRole('button', { name: 'Save changes' })).toHaveAttribute('type', 'submit');
    expect(screen.queryByRole('button', { name: 'Save draft' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Submit for approval' })).toBeNull();
  });

  it('saves with one PUT and never calls /submit', async () => {
    renderForm({ mode: 'edit', project: editProject({ approval_state: state, owner_user_id: 'u-me' } as never) });
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(callsTo('PUT', '/project-sales/projects/p1').length).toBeGreaterThan(0));
    expect(calls.filter((c) => c.url.includes('/submit'))).toHaveLength(0);
  });
});

describe('pins: unapproved registrations keep the salesperson footer (green by design)', () => {
  it('own draft in edit mode: Save draft and Submit for approval', () => {
    granted = new Set(SUBMIT_ONLY);
    renderForm({ mode: 'edit', project: editProject({ approval_state: 'draft', owner_user_id: 'u-me' } as never) });
    expect(screen.getByRole('button', { name: 'Save draft' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Submit for approval' })).toBeInTheDocument();
  });
});
