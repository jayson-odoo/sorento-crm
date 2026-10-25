/**
 * ProjectForm in review mode, and the review page around it (PROJECT-REG-PORTAL UAC B3, B8,
 * B9, E2, G3; PLAN D5).
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

describe('ProjectForm review mode: prefill (D5)', () => {
  it('fills the title, the matched parties and type, State and Mukim from the registration', async () => {
    renderForm();

    expect(
      (screen.getByLabelText(/project title/i) as HTMLTextAreaElement).value,
    ).toBe('CADANGAN BLOK PEJABAT DI ATAS LOT 7001, MUKIM KULAI');
    await waitFor(() => expect(select(/^Developer/).value).toBe('d1'));
    await waitFor(() => expect(select('Project type').value).toBe('ty1'));
    await waitFor(() => expect(select('State').value).toBe('Johor'));
    expect((screen.getByLabelText('Mukim') as HTMLInputElement).value).toBe(
      'Kulai',
    );
    await waitFor(() => expect(select(/architect/i).value).toBe('a1'));
  });

  it('owner is the CRM user linked to the contact', async () => {
    renderForm();
    await waitFor(() => expect(select('Salesperson').value).toBe('u-2'));
  });

  it('a name the server could not match stays empty and shows the typed name as a hint', async () => {
    renderForm(
      registration({
        prefill: {
          developer_party_id: null,
          architect_party_id: 'a1',
          main_contractor_party_id: null,
          type_id: 'ty1',
        },
      }),
    );

    await waitFor(() => expect(select(/^Developer/).value).toBe(''));
    expect(
      screen.getByText('Typed: Example Developer Sdn Bhd'),
    ).toBeInTheDocument();
    expect(screen.getByText('Typed: Unmatched Builders')).toBeInTheDocument();
  });
});

describe('ProjectForm review mode: what it does not have (D5, G3)', () => {
  it('has no Check button, no clash panel and no Join / Dispute, and never asks for a clash preview', async () => {
    previewClashes.mockResolvedValue({
      candidates: [
        {
          project_id: 'p9',
          project_code: 'PRJ-000009',
          title: 'CADANGAN BLOK PEJABAT DI ATAS LOT 7001',
          outcome: 'open',
          owner_name: 'Aina',
          brands: [],
          similarity: 1,
          blocks: true,
        },
      ],
      would_block: true,
    });
    renderForm();
    await waitFor(() => expect(select(/^Developer/).value).toBe('d1'));

    expect(screen.queryByRole('button', { name: /^check/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /join/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /dispute/i })).toBeNull();
    expect(
      screen.queryByRole('button', { name: /blocked by an existing project/i }),
    ).toBeNull();
    expect(previewClashes).not.toHaveBeenCalled();
  });

  it('has no Lead picker, and the foot CTAs are Approve and Reject only', async () => {
    renderForm();
    await waitFor(() => expect(select(/^Developer/).value).toBe('d1'));

    expect(screen.queryByLabelText(/^lead/i)).toBeNull();
    expect(screen.getByRole('button', { name: 'Approve' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reject' })).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /register project|save changes/i }),
    ).toBeNull();
  });

  it('the legacy-only fields (Distributor, Customer, Your ref, Sales agent, Date) are not inputs here', async () => {
    renderForm();
    await waitFor(() => expect(select(/^Developer/).value).toBe('d1'));

    for (const label of [
      /distributor/i,
      /^customer/i,
      /your ref/i,
      /sales agent/i,
      /^date$/i,
    ]) {
      expect(screen.queryByLabelText(label)).toBeNull();
    }
  });

  it('an approved registration is shown, not editable: no Approve or Reject', async () => {
    renderForm(
      registration({
        status: 'approved',
        project_id: 'p1',
        project_code: 'PPF2610005',
      }),
    );
    await waitFor(() => expect(select(/^Developer/).value).toBe('d1'));

    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Reject' })).toBeNull();
  });
});

describe('ProjectForm review mode: Approve (B5, B8)', () => {
  it('Approve with no developer shows the field error and does not call the service', async () => {
    renderForm(
      registration({
        prefill: {
          developer_party_id: null,
          architect_party_id: null,
          main_contractor_party_id: null,
          type_id: 'ty1',
        },
      }),
    );
    await waitFor(() => expect(select('Project type').value).toBe('ty1'));

    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));

    expect(
      await screen.findByText('Developer is required.'),
    ).toBeInTheDocument();
    expect(svc.approveProjectRegistration).not.toHaveBeenCalled();
  });

  it('Approve sends the registration id and the form body with state and mukim', async () => {
    renderForm();
    await waitFor(() => expect(select(/^Developer/).value).toBe('d1'));
    await waitFor(() => expect(select('Salesperson').value).toBe('u-2'));

    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));

    await waitFor(() =>
      expect(svc.approveProjectRegistration).toHaveBeenCalledTimes(1),
    );
    const [id, body] = svc.approveProjectRegistration.mock.calls[0];
    expect(id).toBe('reg-1');
    expect(body).toEqual(
      expect.objectContaining({
        title: 'CADANGAN BLOK PEJABAT DI ATAS LOT 7001, MUKIM KULAI',
        developer_party_id: 'd1',
        type_id: 'ty1',
        owner_user_id: 'u-2',
        state: 'Johor',
        mukim: 'Kulai',
        architect_party_id: 'a1',
      }),
    );
    expect((body as Record<string, unknown>).lead_id ?? null).toBeNull();
    await waitFor(() =>
      expect(push).toHaveBeenCalledWith('/project-sales/registrations'),
    );
  });

  it('the admin can change State and Mukim before approving, and the change is what is sent', async () => {
    renderForm();
    await waitFor(() => expect(select('State').value).toBe('Johor'));

    fireEvent.change(select('State'), { target: { value: 'Selangor' } });
    fireEvent.change(screen.getByLabelText('Mukim'), {
      target: { value: 'Petaling' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));

    await waitFor(() =>
      expect(svc.approveProjectRegistration).toHaveBeenCalled(),
    );
    expect(svc.approveProjectRegistration.mock.calls[0][1]).toEqual(
      expect.objectContaining({ state: 'Selangor', mukim: 'Petaling' }),
    );
  });

  it('a 409 exact duplicate shows its message and stays on the form', async () => {
    svc.approveProjectRegistration.mockRejectedValue(
      new Error(
        'PPF2509012 already has this developer and title. Change the title, e.g. add the phase.',
      ),
    );
    renderForm();
    await waitFor(() => expect(select(/^Developer/).value).toBe('d1'));

    fireEvent.click(screen.getByRole('button', { name: 'Approve' }));

    // Fix round 1 (N13): the hook's toast is the one surface for the server's message.
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('PPF2509012 already has this developer and title'),
      ),
    );
    expect(screen.queryByRole('alert')).toBeNull();
    expect(push).not.toHaveBeenCalled();
  });
});

describe('ProjectForm review mode: Reject (B9)', () => {
  it('Reject opens a reason dialog; a blank reason cannot be sent', async () => {
    renderForm();
    await waitFor(() => expect(select(/^Developer/).value).toBe('d1'));

    fireEvent.click(screen.getByRole('button', { name: 'Reject' }));
    const dialog = await screen.findByRole('dialog');
    const send = within(dialog).getByRole('button', { name: 'Reject' });
    expect(send).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText(/reason/i), {
      target: { value: '   ' },
    });
    expect(send).toBeDisabled();
    expect(svc.rejectProjectRegistration).not.toHaveBeenCalled();
  });

  it('a reason is sent with the registration id and the page returns to the queue', async () => {
    renderForm();
    await waitFor(() => expect(select(/^Developer/).value).toBe('d1'));

    fireEvent.click(screen.getByRole('button', { name: 'Reject' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText(/reason/i), {
      target: { value: 'Already registered by Bakar' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Reject' }));

    await waitFor(() =>
      expect(svc.rejectProjectRegistration).toHaveBeenCalledWith(
        'reg-1',
        'Already registered by Bakar',
      ),
    );
    await waitFor(() =>
      expect(push).toHaveBeenCalledWith('/project-sales/registrations'),
    );
  });
});

describe('Registration review page (B3, G3)', () => {
  it('shows Date, Sales agent (the name), Distributor, Customer and Your ref as read-only text under the header', async () => {
    svc.getProjectRegistration.mockResolvedValue(registration());
    renderWith(<ProjectRegistrationReview id="reg-1" />);

    expect(await screen.findByText('Aminah Example')).toBeInTheDocument();
    for (const text of [
      'Example Distribution Sdn Bhd',
      'Example Customer Sdn Bhd',
      'REF-ZZT-1',
    ]) {
      expect(screen.getByText(text)).toBeInTheDocument();
    }
    for (const label of [
      'Date',
      'Sales agent',
      'Distributor',
      'Customer',
      'Your ref',
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.queryByText('Possible duplicate:')).toBeNull();
  });

  it('the Possible duplicate line links every project to /project-sales/<project_id>', async () => {
    svc.getProjectRegistration.mockResolvedValue(
      registration({
        possible_duplicates: [
          {
            project_id: 'proj-77',
            project_code: 'PPF2509012',
            title: 'KILANG ALPHA LOT 7001',
          },
          {
            project_id: 'proj-78',
            project_code: 'PRJ-000041',
            title: 'GUDANG BETA KULAI',
          },
        ],
      }),
    );
    renderWith(<ProjectRegistrationReview id="reg-1" />);

    expect(await screen.findByText('Possible duplicate:')).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'PPF2509012 KILANG ALPHA LOT 7001' }),
    ).toHaveAttribute('href', '/project-sales/proj-77');
    expect(
      screen.getByRole('link', { name: 'PRJ-000041 GUDANG BETA KULAI' }),
    ).toHaveAttribute('href', '/project-sales/proj-78');
    // Join / Dispute never appears for a duplicate in the queue.
    expect(screen.queryByRole('button', { name: /join|dispute/i })).toBeNull();
  });

  it('a possible duplicate does not stop Approve', async () => {
    svc.getProjectRegistration.mockResolvedValue(
      registration({
        possible_duplicates: [
          {
            project_id: 'proj-77',
            project_code: 'PPF2509012',
            title: 'KILANG ALPHA',
          },
        ],
      }),
    );
    renderWith(<ProjectRegistrationReview id="reg-1" />);

    await waitFor(() => expect(select(/^Developer/).value).toBe('d1'));
    expect(screen.getByRole('button', { name: 'Approve' })).toBeEnabled();
  });

  it('a rejected registration shows its reason', async () => {
    svc.getProjectRegistration.mockResolvedValue(
      registration({
        status: 'rejected',
        reject_reason: 'Already registered by Bakar',
      }),
    );
    renderWith(<ProjectRegistrationReview id="reg-1" />);

    expect(
      await screen.findByText(/Already registered by Bakar/),
    ).toBeInTheDocument();
  });

  it('a failed load shows the error', async () => {
    svc.getProjectRegistration.mockRejectedValue(
      new Error('Registration not found'),
    );
    renderWith(<ProjectRegistrationReview id="reg-9" />);

    expect(
      await screen.findByText('Registration not found'),
    ).toBeInTheDocument();
  });
});
