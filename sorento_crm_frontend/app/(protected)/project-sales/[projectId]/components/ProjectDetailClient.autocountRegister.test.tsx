/**
 * AC-PROJECT-REGISTER Phase 2 (red): register a CRM project in AutoCount from the project page.
 *
 * UAC `documentation/plans/autocount/ac-project-register-acceptance-criteria.md` R16-R18.
 *
 *   R16 Switch on + `projects.autocount.write`: an approved, not lost, not registered project has
 *       the gear item "Register in AutoCount". Greyed with the reason when `can_register` is false.
 *       Pressing it POSTs the register route and the shared AutoCount result dialog shows the answer.
 *   R17 A registered project shows a Badge with its AutoCount number (title "AutoCount number") and
 *       the item is gone. The badge is a stored fact, so it shows whatever the switch is set to.
 *   R18 Switch off or no permission: no item, no badge, and the register route is never called.
 *
 * Mocked at the network edge (`apiFetch`), so the new services
 * (`getAutocountRegisterSwitch` / `getProjectAutocountRegister` / `registerProjectInAutocount`)
 * and hooks (`useAutocountRegisterAccess` / `useProjectAutocountRegister` /
 * `useRegisterProjectInAutocount`) run for real. The register switch has its own app-config field
 * (`project_autocount_register_enabled`); the quotation/sales-order write switch is held OFF here.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Project } from '../../_shared/types/project.types';
import type { StatusGraph } from '@/app/(protected)/system-management/status-graphs/types/statusGraph.types';

// ── jsdom polyfills Radix's dropdown / dialog need ───────────────────────────
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = vi.fn();
Element.prototype.hasPointerCapture = vi.fn();
Element.prototype.setPointerCapture = vi.fn();
Element.prototype.releasePointerCapture = vi.fn();

const WRITE = 'projects.autocount.write';
const ITEM = 'Register in AutoCount';
const WAITING = 'Waiting for AutoCount';
const BADGE_TITLE = 'AutoCount number';

const apiFetch = vi.fn();
let hasWrite = true;
let switchOn = true;
let registerStatus: Record<string, unknown>;
let registerAnswer: Record<string, unknown>;
let projectFixture: Project;

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/p1',
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, apiFetch: (...args: unknown[]) => apiFetch(...args) };
});

vi.mock('@/components/common/ListPager', () => ({
  __esModule: true,
  default: () => <div data-testid="pager-slot" />,
}));

vi.mock('@/components/common/ActivitiesNotesPanel/EntityActivitiesLayout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => (slug === WRITE ? hasWrite : true),
  useHasAnyPermission: (slugs: string[]) => slugs.some((slug) => (slug === WRITE ? hasWrite : true)),
  usePermissions: () => ({ permissions: hasWrite ? [WRITE] : [], permissionSet: new Set(hasWrite ? [WRITE] : []) }),
}));

vi.mock('@/services/userSelectService', () => ({
  getUserLookup: vi.fn(async () => [{ id: 'u-1', name: 'Staff One' }]),
}));

vi.mock('../../_shared/hooks/useProjects', () => ({
  useProjectRelatedRecords: () => ({ data: undefined }),
  projectsPagerQuery: {
    listQueryKey: () => ['projects'],
    fetchPage: async () => ({ data: [], pagination: { total: 0 } }),
  },
  useProject: () => ({ data: projectFixture, isLoading: false, isError: false }),
  usePartyRoles: () => ({ data: [] }),
  useChangeProjectStatus: () => ({ mutate: vi.fn(), isPending: false }),
  useSetProjectOutcome: () => ({ mutate: vi.fn(), isPending: false }),
  useQuotationLossReasons: () => ({ data: [] }),
  useDeleteProject: () => ({ mutateAsync: vi.fn() }),
  useUpdateProject: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
  useCollaborators: () => ({ data: [], isLoading: false }),
  useTakeoverRequests: () => ({ data: [] }),
  useTakeoverMutations: () => ({
    decide: { mutate: vi.fn(), isPending: false },
    request: { mutateAsync: vi.fn(), isPending: false },
  }),
}));

const graphFixture: StatusGraph = {
  entity_type: 'project',
  requested_scope_id: null,
  resolved_scope_id: null,
  is_fork: false,
  statuses: [
    {
      id: 's-quoted',
      entity_type: 'project',
      scope_id: null,
      key: 'quoted',
      label: 'Quoted',
      category: null,
      color_hex: null,
      description: null,
      sort_order: 3,
      is_initial: false,
      is_terminal: false,
      is_active: true,
      is_archived: false,
      is_default: false,
      is_system: false,
    } as StatusGraph['statuses'][number],
  ],
  transitions: [],
};
vi.mock('@/app/(protected)/project-sales/_shared/hooks/useProjectStatusGraph', () => ({
  useProjectStatusGraph: () => ({ data: graphFixture }),
}));

import { ProjectDetailClient } from './ProjectDetailClient';

function json(body: unknown, status = 200): Response {
  return {
    ok: status < 400,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
    headers: new Headers(),
    clone() {
      return this;
    },
  } as unknown as Response;
}

/** An approved, open (not lost) project that is not in AutoCount yet. */
function project(overrides: Record<string, unknown> = {}): Project {
  return {
    id: 'p1',
    project_code: 'PRJ-000001',
    title: 'Menara Ujian',
    outcome: 'open',
    approval_state: 'approved',
    is_critical: false,
    brands: [],
    brand_ids: [],
    next_action_overdue: false,
    stale_level: 0,
    is_unattended: false,
    open_task_count: 0,
    can_edit: true,
    status_id: 's-quoted',
    status_key: 'quoted',
    status_label: 'Quoted',
    autocount_project_no: null,
    autocount_registered_at: null,
    ...overrides,
  } as unknown as Project;
}

function statusAnswer(overrides: Record<string, unknown> = {}) {
  return {
    registered: false,
    project_no: null,
    registered_at: null,
    eligible: true,
    can_register: true,
    reason: null,
    ...overrides,
  };
}

function registerCalls(method?: 'GET' | 'POST') {
  return apiFetch.mock.calls.filter(([url, init]) => {
    if (!String(url).includes('/project-sales/projects/p1/autocount-register')) return false;
    if (!method) return true;
    const sent = String((init as RequestInit | undefined)?.method ?? 'GET').toUpperCase();
    return sent === method;
  });
}

function renderDetail() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ProjectDetailClient projectId="p1" />
    </QueryClientProvider>,
  );
}

async function settled() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 50));
  });
}

async function openGear() {
  fireEvent.pointerDown(screen.getByRole('button', { name: 'Project actions' }), {
    button: 0,
    ctrlKey: false,
  });
  await screen.findByRole('menu');
}

beforeEach(() => {
  vi.clearAllMocks();
  hasWrite = true;
  switchOn = true;
  projectFixture = project();
  registerStatus = statusAnswer();
  registerAnswer = {
    outcome: 'done',
    message: 'PJ-0001 registered in AutoCount',
    doc_no: 'PJ-0001',
  };
  apiFetch.mockImplementation(async (url: string, init?: RequestInit) => {
    const path = String(url);
    if (path.includes('settings/app-config')) {
      return json({
        project_autocount_write_enabled: false,
        project_autocount_register_enabled: switchOn,
      });
    }
    if (path.includes('/project-sales/projects/p1/autocount-register')) {
      const method = String(init?.method ?? 'GET').toUpperCase();
      return json(method === 'POST' ? registerAnswer : registerStatus);
    }
    return json({ detail: 'Not Found' }, 404);
  });
});

describe('R16: the gear item "Register in AutoCount"', () => {
  it('is offered on an approved, open, unregistered project and pressing it shows the answer', async () => {
    renderDetail();
    await waitFor(() => expect(registerCalls('GET').length).toBeGreaterThan(0));
    await settled();
    await openGear();

    const item = await screen.findByRole('menuitem', { name: new RegExp(ITEM) });
    expect(item).not.toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(item);

    await waitFor(() => expect(registerCalls('POST')).toHaveLength(1));
    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('PJ-0001 registered in AutoCount')).toBeInTheDocument();
  });

  it('is greyed with "Waiting for AutoCount" when can_register is false (R7)', async () => {
    registerStatus = statusAnswer({ can_register: false, reason: WAITING });
    renderDetail();
    await waitFor(() => expect(registerCalls('GET').length).toBeGreaterThan(0));
    await settled();
    await openGear();

    const item = await screen.findByRole('menuitem', { name: new RegExp(ITEM) });
    expect(item).toHaveAttribute('aria-disabled', 'true');
    expect(document.body.innerHTML).toContain(WAITING);
    expect(registerCalls('POST')).toHaveLength(0);
  });

  it('keeps a way to try again from the menu after a refusal', async () => {
    registerAnswer = { outcome: 'refused', message: 'AutoCount refused the project code', doc_no: null };
    renderDetail();
    await waitFor(() => expect(registerCalls('GET').length).toBeGreaterThan(0));
    await settled();
    await openGear();
    fireEvent.click(await screen.findByRole('menuitem', { name: new RegExp(ITEM) }));

    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('AutoCount refused the project code')).toBeInTheDocument();
    fireEvent.keyDown(dialog, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());

    await openGear();
    expect(
      screen.getByRole('menuitem', { name: new RegExp(`${ITEM}|Try again`) }),
    ).not.toHaveAttribute('aria-disabled', 'true');
  });
});

describe('R17: a registered project shows its AutoCount number', () => {
  it.each([true, false])('shows the Badge and no menu item (switch on: %s)', async (on) => {
    switchOn = on;
    projectFixture = project({
      autocount_project_no: 'PJ-0009',
      autocount_registered_at: '2026-11-13T03:00:00',
    });
    registerStatus = statusAnswer({
      registered: true,
      project_no: 'PJ-0009',
      registered_at: '2026-11-13T03:00:00',
      can_register: false,
    });
    renderDetail();
    await settled();

    const badge = await screen.findByTitle(BADGE_TITLE);
    expect(badge).toHaveTextContent('PJ-0009');

    await openGear();
    expect(screen.queryByRole('menuitem', { name: new RegExp(ITEM) })).toBeNull();
  });
});

describe('R18: switch off or no permission changes nothing on the page', () => {
  it.each([
    ['switch off', () => (switchOn = false)],
    ['no permission', () => (hasWrite = false)],
  ])('%s: no item, no badge, the register route is never called', async (_label, arrange) => {
    arrange();
    renderDetail();
    await waitFor(() =>
      expect(
        apiFetch.mock.calls.some(([url]) => String(url).includes('settings/app-config')) || !hasWrite,
      ).toBe(true),
    );
    await settled();

    expect(screen.queryByTitle(BADGE_TITLE)).toBeNull();
    // Mark won keeps the gear present on an open project, so the menu can be opened.
    await openGear();
    expect(screen.queryByRole('menuitem', { name: new RegExp(ITEM) })).toBeNull();
    expect(screen.queryByText(WAITING)).toBeNull();
    expect(registerCalls()).toHaveLength(0);
  });
});
