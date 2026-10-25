/**
 * RW14 - the registration review mode is gone; a portal project is edited in the ordinary edit
 * form (PLAN R7, R11).
 *
 * - `ProjectForm` has no `review` mode, no Approve / Reject foot and no registrations route.
 * - While an approver has not picked a Developer party, the form shows what the salesperson
 *   typed under Developer ("Typed: <developer_name>", from `project.registration`), the same
 *   hint under Architect and Main contractor; it disappears once a party is picked.
 * - Editing a pending project keeps the rest of the form as it is for any project.
 */
import fs from 'node:fs';
import path from 'node:path';
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Project } from '../types/project.types';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  usePathname: () => '/project-sales/registrations/reg-1',
  useRouter: () => ({ push, replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
}));

vi.mock('next-auth/react', () => ({
  useSession: () => ({
    data: { user: { id: 'u-me', name: 'Me' } },
    status: 'authenticated',
  }),
}));

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
  usePermissions: () => ({
    permissions: [],
    permissionSet: new Set(),
    isLoading: false,
  }),
}));

const getUserLookup = vi.fn();
vi.mock('@/services/userSelectService', () => ({
  getUserLookup: (...args: unknown[]) => getUserLookup(...args),
}));

vi.mock(
  '@/app/(protected)/master-data-management/shared/hooks/use-brand-select-query',
  () => ({
    useBrandSelectQuery: () => ({ data: [], isLoading: false }),
  }),
);

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

const toast = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  custom: vi.fn(),
}));
vi.mock('@/lib/toast', () => ({ toast }));

const listParties = vi.fn();
const listProjectTypes = vi.fn();
const listProjectTemplates = vi.fn();
const previewClashes = vi.fn();
const registerProject = vi.fn();
vi.mock('../services/projectService', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../services/projectService')>();
  return {
    ...actual,
    listParties: (...args: unknown[]) => listParties(...args),
    listProjectTypes: (...args: unknown[]) => listProjectTypes(...args),
    listProjectTemplates: (...args: unknown[]) => listProjectTemplates(...args),
    previewClashes: (...args: unknown[]) => previewClashes(...args),
    registerProject: (...args: unknown[]) => registerProject(...args),
    listLeads: vi.fn(async () => ({
      data: [],
      pagination: { total: 0, page: 1, limit: 20 },
    })),
  };
});

type Option = { value: string; label: string };

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    id,
    value,
    onChange,
    options,
    disabled,
  }: {
    id?: string;
    value: string;
    onChange: (next: string) => void;
    options?: Option[];
    disabled?: boolean;
  }) => (
    // eslint-disable-next-line no-restricted-syntax -- test stub for SearchableSelect
    <select
      id={id}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="" />
      {(options ?? []).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: ({ id }: { id?: string }) => (
    <select id={id} multiple />
  ),
}));

vi.mock('@/components/ui/date-range-picker', () => ({
  DateRangePicker: ({ id }: { id?: string }) => <input id={id} />,
}));

import { ProjectForm } from './ProjectForm';

const DEVELOPER = { id: 'd1', party_type: 'developer', name: 'Example Developer Sdn Bhd', is_active: true };
const ARCHITECT = { id: 'a1', party_type: 'architect', name: 'Example Architects', is_active: true };

function pendingProject(over: Record<string, unknown> = {}): Project {
  return {
    id: 'p1',
    project_code: null,
    title: 'CADANGAN BLOK PEJABAT DI ATAS LOT 7001, MUKIM KULAI',
    outcome: 'open',
    is_critical: false,
    approval_state: 'pending',
    developer_party_id: null,
    developer_name: null,
    type_id: null,
    type_name: null,
    template_id: null,
    template_name: null,
    owner_user_id: 'u-2',
    owner_name: 'Aina Linked',
    state: 'Johor',
    mukim: 'Kulai',
    architect_party_id: null,
    architect_name: null,
    main_contractor_party_id: null,
    main_contractor_name: null,
    brands: [],
    brand_ids: [],
    lead_id: null,
    lead_code: null,
    next_action_overdue: false,
    stale_level: 0,
    is_unattended: false,
    open_task_count: 0,
    can_edit: true,
    registration: {
      sales_agent_name: 'Aminah Example',
      distributor_name: 'Example Distribution Sdn Bhd',
      customer_name: 'Example Customer Sdn Bhd',
      your_ref: 'REF-ZZT-1',
      type_of_building: 'Office',
      developer_name: 'Example Developer Sdn Bhd',
      main_contractor_name: 'Unmatched Builders',
      architect_name: 'Example Architects',
    },
    ...over,
  } as unknown as Project;
}

function renderEdit(project: Project) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ProjectForm mode="edit" project={project} />
    </QueryClientProvider>,
  );
}

const select = (label: RegExp | string) => screen.getByLabelText(label) as HTMLSelectElement;

beforeEach(() => {
  vi.clearAllMocks();
  listParties.mockImplementation(async (params: { party_type?: string }) => {
    const byType: Record<string, unknown[]> = {
      developer: [DEVELOPER],
      architect: [ARCHITECT],
      main_contractor: [],
    };
    return { data: byType[params.party_type ?? ''] ?? [], pagination: { total: 1, page: 1, limit: 200 } };
  });
  listProjectTypes.mockResolvedValue([]);
  listProjectTemplates.mockResolvedValue([]);
  previewClashes.mockResolvedValue({ candidates: [], would_block: false });
  getUserLookup.mockResolvedValue([
    { id: 'u-me', name: 'Me' },
    { id: 'u-2', name: 'Aina Linked' },
  ]);
});

describe('editing a pending project: the typed name hint (RW14)', () => {
  it('shows "Typed: <developer_name>" under Developer while no party is picked', async () => {
    renderEdit(pendingProject());
    await waitFor(() => expect(select(/^Developer/).value).toBe(''));
    expect(screen.getByText('Typed: Example Developer Sdn Bhd')).toBeInTheDocument();
  });

  it('shows the hint under Architect and Main contractor too', async () => {
    renderEdit(pendingProject());
    await waitFor(() => expect(select(/^Developer/).value).toBe(''));
    expect(screen.getByText('Typed: Example Architects')).toBeInTheDocument();
    expect(screen.getByText('Typed: Unmatched Builders')).toBeInTheDocument();
  });

  it('the hint goes once the approver picks the party', async () => {
    renderEdit(pendingProject());
    await waitFor(() => expect(within_options(select(/^Developer/))).toContain('d1'));
    fireEvent.change(select(/^Developer/), { target: { value: 'd1' } });
    await waitFor(() => expect(screen.queryByText('Typed: Example Developer Sdn Bhd')).toBeNull());
  });

  it('no Developer hint when the project already has the party; the unpicked ones keep theirs', async () => {
    renderEdit(pendingProject({ developer_party_id: 'd1', developer_name: 'Example Developer Sdn Bhd' }));
    await waitFor(() => expect(select(/^Developer/).value).toBe('d1'));
    expect(screen.queryByText('Typed: Example Developer Sdn Bhd')).toBeNull();
    expect(screen.getByText('Typed: Example Architects')).toBeInTheDocument();
    expect(screen.getByText('Typed: Unmatched Builders')).toBeInTheDocument();
  });

  it('no hint at all once every party is picked', async () => {
    renderEdit(
      pendingProject({
        developer_party_id: 'd1',
        developer_name: 'Example Developer Sdn Bhd',
        architect_party_id: 'a1',
        architect_name: 'Example Architects',
        main_contractor_party_id: 'c1',
        main_contractor_name: 'Unmatched Builders',
      }),
    );
    await waitFor(() => expect(select(/^Developer/).value).toBe('d1'));
    expect(screen.queryByText(/^Typed:/)).toBeNull();
  });

  it('no hint for a staff project, which has no registration block', async () => {
    renderEdit(
      pendingProject({
        approval_state: null,
        project_code: 'PRJ-000142',
        registration: null,
        developer_party_id: null,
        developer_name: null,
      }),
    );
    await waitFor(() => expect(select(/^Developer/).value).toBe(''));
    expect(screen.queryByText(/^Typed:/)).toBeNull();
  });

  it('keeps the title, State and Mukim of the registration in the ordinary fields', async () => {
    renderEdit(pendingProject());
    expect((screen.getByLabelText(/project title/i) as HTMLTextAreaElement).value).toBe(
      'CADANGAN BLOK PEJABAT DI ATAS LOT 7001, MUKIM KULAI',
    );
    await waitFor(() => expect(select('State').value).toBe('Johor'));
    expect((screen.getByLabelText('Mukim') as HTMLInputElement).value).toBe('Kulai');
  });

  it('has no Approve or Reject button in the form: those live in the project header', async () => {
    renderEdit(pendingProject());
    await waitFor(() => expect(select(/^Developer/).value).toBe(''));
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull();
  });
});

function within_options(el: HTMLSelectElement): string[] {
  return Array.from(el.options).map((o) => o.value);
}

describe('the review mode is removed from the source (RW14)', () => {
  const root = path.resolve(__dirname, '../../../../..');
  const form = fs.readFileSync(path.join(__dirname, 'ProjectForm.tsx'), 'utf8');

  it('ProjectForm no longer has a review mode, a registration prop or an approve hook', () => {
    expect(form).not.toMatch(/mode:\s*'review'/);
    expect(form).not.toMatch(/mode === 'review'/);
    expect(form).not.toMatch(/registration=/);
    expect(form).not.toMatch(/useApproveProjectRegistration|useRejectProjectRegistration/);
    expect(form).not.toMatch(/projectRegistration/);
    expect(form).not.toMatch(/\/project-sales\/registrations/);
  });

  it('the registrations pages, list, review and hooks are deleted', () => {
    const dir = path.join(root, 'app/(protected)/project-sales/registrations');
    expect(fs.existsSync(dir)).toBe(false);
  });

  it('the registrations service and types are deleted', () => {
    expect(fs.existsSync(path.join(root, 'services/projectRegistrationService.ts'))).toBe(false);
    expect(fs.existsSync(path.join(root, 'types/projectRegistration.ts'))).toBe(false);
  });

  it('nothing under app/ or config/ still links to the removed pages', () => {
    const offenders: string[] = [];
    const walk = (dir: string) => {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        if (entry.name === 'node_modules' || entry.name === '.next') continue;
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) walk(full);
        else if (/\.(ts|tsx)$/.test(entry.name) && !/\.test\.(ts|tsx)$/.test(entry.name)) {
          if (fs.readFileSync(full, 'utf8').includes('/project-sales/registrations')) offenders.push(full);
        }
      }
    };
    walk(path.join(root, 'app'));
    walk(path.join(root, 'config'));
    expect(offenders).toEqual([]);
  });
});
