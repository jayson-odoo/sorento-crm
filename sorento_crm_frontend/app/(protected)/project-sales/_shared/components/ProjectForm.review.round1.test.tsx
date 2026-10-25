/**
 * ProjectForm review mode, fix round 1 (S9 owner select, N13 one error surface, N14 link).
 *
 * Mocked at the service boundary (`@/services/projectRegistrationService` and
 * `../services/projectService`); the real hooks run. Select widgets are plain controls
 * (same doubles as ProjectForm.test.tsx) so the tests pin ProjectForm's own wiring.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ProjectRegistrationDetail } from '@/types/projectRegistration';

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

const held = vi.hoisted(() => new Set<string>());
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => held.has(slug),
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

const svc = vi.hoisted(() => ({
  getProjectRegistration: vi.fn(),
  approveProjectRegistration: vi.fn(),
  rejectProjectRegistration: vi.fn(),
  getProjectRegistrations: vi.fn(),
}));
vi.mock('@/services/projectRegistrationService', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  ...svc,
}));

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
import ProjectRegistrationReview from '../../registrations/components/ProjectRegistrationReview';

const DEVELOPER = {
  id: 'd1',
  party_type: 'developer',
  name: 'Example Developer Sdn Bhd',
  is_active: true,
};
const ARCHITECT = {
  id: 'a1',
  party_type: 'architect',
  name: 'Example Architects',
  is_active: true,
};
const TYPE_OFFICE = {
  id: 'ty1',
  name: 'Office',
  code: 'OFFICE',
  derives_delivery_from_launch: false,
  sort_order: 1,
  is_active: true,
};

function registration(
  over: Partial<ProjectRegistrationDetail> = {},
): ProjectRegistrationDetail {
  return {
    id: 'reg-1',
    status: 'pending',
    reject_reason: null,
    submitted_at: '2026-10-02T08:00:00',
    decided_at: null,
    decided_by_name: null,
    applicant_user_id: 'u-2',
    project_id: null,
    project_code: null,
    title: 'CADANGAN BLOK PEJABAT DI ATAS LOT 7001, MUKIM KULAI',
    distributor_name: 'Example Distribution Sdn Bhd',
    customer_id: 'cust-1',
    customer_name: 'Example Customer Sdn Bhd',
    type_of_building: 'Office',
    state: 'Johor',
    mukim: 'Kulai',
    your_ref: 'REF-ZZT-1',
    developer_name: 'Example Developer Sdn Bhd',
    main_contractor_name: 'Unmatched Builders',
    architect_name: 'Example Architects',
    sales_agent_name: 'Aminah Example',
    possible_duplicates: [],
    prefill: {
      developer_party_id: 'd1',
      architect_party_id: 'a1',
      main_contractor_party_id: null,
      type_id: 'ty1',
    },
    ...over,
  };
}

function renderWith(node: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{node}</QueryClientProvider>,
  );
}

const renderForm = (reg = registration()) =>
  renderWith(<ProjectForm mode="review" registration={reg} />);

const select = (label: RegExp | string) =>
  screen.getByLabelText(label) as HTMLSelectElement;

beforeEach(() => {
  vi.clearAllMocks();
  held.clear();
  listParties.mockImplementation(async (params: { party_type?: string }) => {
    const byType: Record<string, unknown[]> = {
      developer: [DEVELOPER],
      architect: [ARCHITECT],
      main_contractor: [],
    };
    return {
      data: byType[params.party_type ?? ''] ?? [],
      pagination: { total: 1, page: 1, limit: 200 },
    };
  });
  listProjectTypes.mockResolvedValue([TYPE_OFFICE]);
  listProjectTemplates.mockResolvedValue([]);
  previewClashes.mockResolvedValue({ candidates: [], would_block: false });
  getUserLookup.mockResolvedValue([
    { id: 'u-me', name: 'Me' },
    { id: 'u-2', name: 'Aina Linked' },
  ]);
  svc.approveProjectRegistration.mockResolvedValue(
    registration({ status: 'approved', project_code: 'PPF2610005' }),
  );
  svc.rejectProjectRegistration.mockResolvedValue(
    registration({ status: 'rejected' }),
  );
});

describe('S9: the Salesperson select follows the manage grant', () => {
  it('is disabled without projects.projects.manage and keeps the applicant', async () => {
    renderForm();
    await waitFor(() => expect(select('Salesperson').value).toBe('u-2'));
    expect(select('Salesperson').disabled).toBe(true);
  });

  it('is enabled for a sales manager', async () => {
    held.add('projects.projects.manage');
    renderForm();
    await waitFor(() => expect(select('Salesperson').value).toBe('u-2'));
    expect(select('Salesperson').disabled).toBe(false);
  });
});

describe('N13: one surface for an approve error', () => {
  it('a refused approval is toasted by the hook and not repeated inline', async () => {
    svc.approveProjectRegistration.mockRejectedValue(
      new Error('PPF2509012 already has this developer and title.'),
    );
    renderForm();
    await waitFor(() => expect(select(/^Developer/).value).toBe('d1'));

    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        'PPF2509012 already has this developer and title.',
      ),
    );
    expect(screen.queryByRole('alert')).toBeNull();
    expect(push).not.toHaveBeenCalled();
  });

  it('the missing developer is still a field error', async () => {
    renderForm(registration({ prefill: { ...registration().prefill, developer_party_id: null } }));
    await waitFor(() => expect(select(/^Developer/).value).toBe(''));

    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));

    expect(await screen.findByText('Developer is required.')).toBeInTheDocument();
    expect(svc.approveProjectRegistration).not.toHaveBeenCalled();
  });
});

describe('N14: the approved registration links to its project', () => {
  it('the PPF code in the meta line is a link to the project', async () => {
    svc.getProjectRegistration.mockResolvedValue(
      registration({ status: 'approved', project_id: 'p-9', project_code: 'PPF2610005' }),
    );
    renderWith(<ProjectRegistrationReview id="reg-1" />);

    const link = await screen.findByRole('link', { name: 'PPF2610005' });
    expect(link).toHaveAttribute('href', '/project-sales/p-9');
  });
});
