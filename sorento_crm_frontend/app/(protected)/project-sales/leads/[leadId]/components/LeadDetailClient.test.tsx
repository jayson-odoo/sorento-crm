/**
 * P1 - LeadDetailClient (AC-A1, AC-A2, AC-A4, AC-A5).
 *
 * What is pinned here:
 *   - the informant renders as names, never as an id, and never as the buyer
 *   - a lead with no buyer says so deliberately and offers the next step
 *   - Accept and Decline belong to the person holding the lead and nobody else
 *   - a decline cannot be sent without a reason
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ProjectLead } from '../../../_shared/types/project.types';
import type { LeadWithAcceptance } from '../../../_shared/types/leadAcceptance.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const getLead = vi.fn();
const updateLead = vi.fn();
const getCustomerPortfolio = vi.fn();
const acceptLead = vi.fn();
const declineLead = vi.fn();
const assignLead = vi.fn();
const getUsersSelect = vi.fn();

let sessionUserId: string | undefined = 'u-ali';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

vi.mock('next-auth/react', () => ({
  useSession: () => ({
    data: sessionUserId ? { user: { id: sessionUserId } } : null,
    status: 'authenticated',
  }),
}));

vi.mock(
  '@/app/(protected)/system-management/status-graphs/hooks/useStatusGraphs',
  () => ({ useStatusGraph: () => ({ data: { statuses: [] }, isLoading: false }) }),
);

vi.mock('../../../_shared/services/projectService', () => ({
  getLead: (...args: unknown[]) => getLead(...args),
  updateLead: (...args: unknown[]) => updateLead(...args),
  getCustomerPortfolio: (...args: unknown[]) => getCustomerPortfolio(...args),
  listParties: vi.fn(async () => ({
    data: [],
    pagination: { total: 0, page: 1, limit: 200 },
  })),
  listProjectTypes: vi.fn(async () => []),
  listProjectTemplates: vi.fn(async () => []),
  listLeads: vi.fn(),
  createLead: vi.fn(),
  changeLeadStatus: vi.fn(),
  previewQualify: vi.fn(),
  qualifyLead: vi.fn(),
  disqualifyLead: vi.fn(),
  reopenLead: vi.fn(),
  deleteLead: vi.fn(),
  listDisqualifyReasons: vi.fn(async () => []),
  getLeadMetrics: vi.fn(),
  listProjects: vi.fn(),
}));

vi.mock('../../../_shared/services/leadAcceptanceService', () => ({
  listAwaitingAcceptance: vi.fn(),
  assignLead: (...args: unknown[]) => assignLead(...args),
  acceptLead: (...args: unknown[]) => acceptLead(...args),
  declineLead: (...args: unknown[]) => declineLead(...args),
  nudgeLeadAssignee: vi.fn(),
}));

vi.mock('@/services/userSelectService', () => ({
  getUsersSelect: (...args: unknown[]) => getUsersSelect(...args),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn() },
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
  }: {
    value: string;
    onChange: (next: string) => void;
    options?: { value: string; label: string }[];
    placeholder?: string;
  }) => (
    <select
      aria-label={placeholder ?? 'select'}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      <option value="">{placeholder ?? ''}</option>
      {(options ?? []).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

vi.mock(
  '@/app/(protected)/order-management/shared/hooks/use-customer-select-query',
  () => ({
    useCustomerSelectQuery: () => ({
      data: [{ id: 'c1', customer_name: 'Sunway Construction', customer_code: 'C-001' }],
      isLoading: false,
    }),
  }),
);

import { LeadDetailClient } from './LeadDetailClient';

function lead(overrides: Partial<LeadWithAcceptance> = {}): ProjectLead {
  const row: LeadWithAcceptance = {
    id: 'l1',
    lead_code: 'LEAD-000001',
    title: 'Tower behind the showroom',
    customer_id: null,
    customer_name: null,
    developer_name: 'Setia Land',
    location: 'Setia Alam',
    outcome: 'open',
    project_count: 0,
    possible_duplicates: [],
    can_edit: true,
    informant_source: 'bci',
    informant_ref: 'BCI-778812',
    informant_party_id: '11111111-1111-1111-1111-111111111111',
    informant_party_label: 'Veritas Architects Sdn Bhd',
    informant_contact_name: 'Lim, QS',
    acceptance_state: 'assigned',
    owner_user_id: 'u-ali',
    owner_name: 'Ali',
    assigned_at: new Date(Date.now() - 50 * 3_600_000).toISOString().replace('Z', ''),
    ...overrides,
  };
  return row as ProjectLead;
}

function renderDetail() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <LeadDetailClient leadId="l1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  sessionUserId = 'u-ali';
  getLead.mockResolvedValue(lead());
  updateLead.mockResolvedValue(lead());
  acceptLead.mockResolvedValue(lead({ acceptance_state: 'accepted' }));
  declineLead.mockResolvedValue(
    lead({ acceptance_state: 'declined', owner_user_id: null, owner_name: null }),
  );
  assignLead.mockResolvedValue(lead());
  getCustomerPortfolio.mockResolvedValue({ leads: [], projects: [] });
  getUsersSelect.mockResolvedValue([
    { id: 'u-siti', name: 'Siti', email: 'siti@x.my' },
  ]);
});

describe('LeadDetailClient', () => {
  it('shows a skeleton while the lead loads', () => {
    getLead.mockReturnValue(new Promise(() => {}));
    const { container } = renderDetail();
    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
  });

  it('reports a load failure instead of looking empty', async () => {
    getLead.mockRejectedValue(new Error('Lead is gone'));
    renderDetail();
    expect(await screen.findByText('Lead is gone')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to leads' })).toBeInTheDocument();
  });

  it('renders the informant by name and never by id', async () => {
    renderDetail();

    expect(await screen.findByText('Who told us')).toBeInTheDocument();
    expect(screen.getByText('Veritas Architects Sdn Bhd')).toBeInTheDocument();
    expect(screen.getByText('Lim, QS')).toBeInTheDocument();
    expect(screen.getByText('BCI-778812')).toBeInTheDocument();
    expect(screen.getByText('BCI')).toBeInTheDocument();
    expect(
      screen.queryByText('11111111-1111-1111-1111-111111111111'),
    ).not.toBeInTheDocument();
  });

  it('says the buyer is not known yet, and offers to set it', async () => {
    renderDetail();

    expect(await screen.findByText('Not known yet')).toBeInTheDocument();
    expect(screen.getByText('No buyer yet')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Set the buyer' }));
    expect(await screen.findByText('Who told us, and who buys')).toBeInTheDocument();
  });

  it('shows the acceptance state and how long it has been waiting', async () => {
    renderDetail();

    expect(
      (await screen.findAllByText('Awaiting acceptance by Ali')).length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText('Waiting 2 days').length).toBeGreaterThan(0);
  });

  it('offers Accept and Decline to the person holding it', async () => {
    renderDetail();

    fireEvent.click(await screen.findByRole('button', { name: /Accept/ }));
    await waitFor(() => expect(acceptLead).toHaveBeenCalledWith('l1'));
  });

  it('hides Accept and Decline from everybody else', async () => {
    sessionUserId = 'u-marketing';
    renderDetail();

    await screen.findByText('Who told us');
    expect(screen.queryByRole('button', { name: /Accept/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Decline$/ })).not.toBeInTheDocument();
    // Marketing can still hand it to somebody else.
    expect(screen.getByRole('button', { name: /Reassign/ })).toBeInTheDocument();
  });

  it('refuses to decline without a reason, and sends the reason when there is one', async () => {
    renderDetail();

    fireEvent.click(await screen.findByRole('button', { name: /^Decline$/ }));

    const dialog = within(await screen.findByRole('dialog'));
    expect(dialog.getByRole('button', { name: 'Decline' })).toBeDisabled();

    fireEvent.change(dialog.getByLabelText(/Reason/), {
      target: { value: 'Outside my area' },
    });
    expect(dialog.getByRole('button', { name: 'Decline' })).toBeEnabled();
    fireEvent.click(dialog.getByRole('button', { name: 'Decline' }));

    await waitFor(() => expect(declineLead).toHaveBeenCalledWith('l1', 'Outside my area'));
  });

  it('assigns to somebody else from the header', async () => {
    sessionUserId = 'u-marketing';
    renderDetail();

    fireEvent.click(await screen.findByRole('button', { name: /Reassign/ }));

    const picker = await screen.findByLabelText('Search people');
    await waitFor(() =>
      expect(screen.getByRole('option', { name: 'Siti' })).toBeInTheDocument(),
    );
    fireEvent.change(picker, { target: { value: 'u-siti' } });
    fireEvent.click(screen.getByRole('button', { name: 'Assign' }));

    await waitFor(() =>
      expect(assignLead).toHaveBeenCalledWith('l1', {
        owner_user_id: 'u-siti',
        note: null,
      }),
    );
  });

  it('records the decline reason on the lead once declined', async () => {
    getLead.mockResolvedValue(
      lead({
        acceptance_state: 'declined',
        owner_user_id: null,
        owner_name: null,
        declined_reason: 'Johor team covers Nusajaya',
        declined_at: '2026-08-01T02:00:00',
      }),
    );
    renderDetail();

    expect(await screen.findByText('Johor team covers Nusajaya')).toBeInTheDocument();
    expect(screen.getAllByText('Declined').length).toBeGreaterThan(0);
  });

  it('offers Assign on a declined lead, which is where marketing picks it back up', async () => {
    sessionUserId = 'u-marketing';
    getLead.mockResolvedValue(
      lead({
        acceptance_state: 'declined',
        owner_user_id: null,
        owner_name: null,
        can_edit: false,
        declined_reason: 'Johor team covers Nusajaya',
      }),
    );
    renderDetail();

    // Not "Reassign": nobody holds it.
    expect(await screen.findByRole('button', { name: /^Assign$/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Reassign/ })).not.toBeInTheDocument();
  });

  it('never sends an owner through the edit form, because that would skip the handshake', async () => {
    renderDetail();

    fireEvent.click(await screen.findByRole('button', { name: 'Edit' }));
    expect(screen.queryByLabelText('Search people')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(updateLead).toHaveBeenCalled());
    const body = updateLead.mock.calls[0][1] as Record<string, unknown>;
    expect(body).not.toHaveProperty('owner_user_id');
  });

  it('saves the informant and the buyer together', async () => {
    renderDetail();

    fireEvent.click(await screen.findByRole('button', { name: 'Edit' }));
    fireEvent.change(await screen.findByLabelText('Not known yet'), {
      target: { value: 'c1' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(updateLead).toHaveBeenCalledWith(
        'l1',
        expect.objectContaining({
          customer_id: 'c1',
          informant_source: 'bci',
          informant_ref: 'BCI-778812',
          informant_contact_name: 'Lim, QS',
          informant_party_id: '11111111-1111-1111-1111-111111111111',
        }),
      ),
    );
  });
});
