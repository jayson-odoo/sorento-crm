/**
 * S2c - LeadsClient (AC-O3, AC-O6).
 *
 * Two things carry the design and are pinned here:
 *   - a duplicate is SURFACED, never enforced, and it names the other person so the
 *     race becomes a conversation
 *   - conversion reads "no decisions yet" rather than 0%, because zero is a different
 *     and wrong claim
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { LeadWithAcceptance } from '../../_shared/types/leadAcceptance.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const listLeads = vi.fn();
const getLeadMetrics = vi.fn();

vi.mock('../../_shared/services/projectService', () => ({
  listLeads: (...args: unknown[]) => listLeads(...args),
  getLeadMetrics: (...args: unknown[]) => getLeadMetrics(...args),
  getLead: vi.fn(),
  createLead: vi.fn(),
  updateLead: vi.fn(),
  changeLeadStatus: vi.fn(),
  previewQualify: vi.fn(),
  qualifyLead: vi.fn(),
  disqualifyLead: vi.fn(),
  reopenLead: vi.fn(),
  deleteLead: vi.fn(),
  listDisqualifyReasons: vi.fn(async () => []),
  getCustomerPortfolio: vi.fn(),
  listProjectTasks: vi.fn(),
  createProjectTask: vi.fn(),
  updateProjectTask: vi.fn(),
  changeTaskStatus: vi.fn(),
  deleteProjectTask: vi.fn(),
  getTaskHistory: vi.fn(),
  listMyTasks: vi.fn(),
  listTemplateTasks: vi.fn(),
  createTemplateTask: vi.fn(),
  updateTemplateTask: vi.fn(),
  deleteTemplateTask: vi.fn(),
  listProjects: vi.fn(),
  getProject: vi.fn(),
  listProjectTypes: vi.fn(),
  listProjectTemplates: vi.fn(),
  listParties: vi.fn(async () => ({ data: [], pagination: { total: 0, page: 1, limit: 50 } })),
  listStakeholders: vi.fn(),
  listCollaborators: vi.fn(),
  listTakeoverRequests: vi.fn(),
  previewClashes: vi.fn(),
  registerProject: vi.fn(),
  updateProject: vi.fn(),
  deleteProject: vi.fn(),
  changeProjectStatus: vi.fn(),
  addStakeholder: vi.fn(),
  updateStakeholder: vi.fn(),
  removeStakeholder: vi.fn(),
  createParty: vi.fn(),
  updateParty: vi.fn(),
  deleteParty: vi.fn(),
  createTakeoverRequest: vi.fn(),
  decideTakeoverRequest: vi.fn(),
  createProjectType: vi.fn(),
  updateProjectType: vi.fn(),
  deleteProjectType: vi.fn(),
  createProjectTemplate: vi.fn(),
  updateProjectTemplate: vi.fn(),
  deleteProjectTemplate: vi.fn(),
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
  () => ({ useCustomerSelectQuery: () => ({ data: [], isLoading: false }) }),
);

import { LeadsClient } from './LeadsClient';

function lead(overrides: Partial<LeadWithAcceptance> = {}): LeadWithAcceptance {
  return {
    id: 'l1',
    lead_code: 'LEAD-000001',
    title: 'Tower behind the showroom',
    customer_id: 'c1',
    customer_name: 'Veritas Architects',
    outcome: 'open',
    project_count: 0,
    possible_duplicates: [],
    can_edit: true,
    ...overrides,
  };
}

const NO_METRICS = {
  total: 0,
  open: 0,
  qualified: 0,
  disqualified: 0,
  decided: 0,
  conversion_rate: null,
  projects_from_leads: 0,
  disqualified_reasons: [],
};

function renderClient() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <LeadsClient />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  listLeads.mockResolvedValue({
    data: [],
    pagination: { total: 0, page: 1, limit: 200 },
  });
  getLeadMetrics.mockResolvedValue(NO_METRICS);
});

describe('LeadsClient', () => {
  it('opens on OPEN leads, because the list is a worklist and not an archive', async () => {
    renderClient();

    await waitFor(() =>
      expect(listLeads).toHaveBeenCalledWith(
        expect.objectContaining({ outcome: ['open'] }),
      ),
    );
  });

  it('says "no decisions yet" instead of 0% conversion', async () => {
    renderClient();

    expect(await screen.findByText('No decisions yet')).toBeInTheDocument();
    expect(screen.queryByText('0%')).not.toBeInTheDocument();
  });

  it('reports a real conversion rate against decided leads', async () => {
    getLeadMetrics.mockResolvedValue({
      ...NO_METRICS,
      total: 5,
      open: 2,
      qualified: 2,
      disqualified: 1,
      decided: 3,
      conversion_rate: 0.6667,
      projects_from_leads: 2,
    });

    renderClient();

    expect(await screen.findByText('67%')).toBeInTheDocument();
    expect(screen.getByText('2 of 3 decided')).toBeInTheDocument();
  });

  it('surfaces a duplicate by naming the other owner, and never as a warning', async () => {
    listLeads.mockResolvedValue({
      data: [
        lead({
          possible_duplicates: [
            { lead_id: 'l2', lead_code: 'LEAD-000002', owner_name: 'Siti' },
          ],
        }),
      ],
      pagination: { total: 1, page: 1, limit: 200 },
    });

    renderClient();

    const hint = await screen.findByText(/Also recorded by Siti/);
    expect(hint).toBeInTheDocument();
    expect(hint).toHaveTextContent(/Leads are not exclusive, so both stand/);
    // No blocking language anywhere: recording a duplicate lead is allowed.
    expect(screen.queryByText(/already registered/i)).not.toBeInTheDocument();
  });

  it('explains that a lead claims nothing when there are none', async () => {
    renderClient();

    expect(await screen.findByText('No open leads')).toBeInTheDocument();
    expect(
      screen.getByText(/it becomes somebody's only when they accept it/i),
    ).toBeInTheDocument();
  });

  it('distinguishes an empty filter result from an empty pipeline', async () => {
    renderClient();
    await screen.findByText('No open leads');

    fireEvent.change(screen.getByLabelText('All outcomes'), {
      target: { value: 'qualified' },
    });

    expect(await screen.findByText('No leads match these filters')).toBeInTheDocument();
  });

  it('shows how many projects a lead produced, because one lead may produce several', async () => {
    listLeads.mockResolvedValue({
      data: [lead({ project_count: 3, outcome: 'qualified' })],
      pagination: { total: 1, page: 1, limit: 200 },
    });

    renderClient();

    expect(await screen.findByText(/3 projects/)).toBeInTheDocument();
  });

  it('shows who told us, that the buyer is unknown, and how long acceptance has waited', async () => {
    listLeads.mockResolvedValue({
      data: [
        lead({
          customer_id: null,
          customer_name: null,
          informant_source: 'bci',
          informant_party_label: 'Veritas Architects Sdn Bhd',
          informant_ref: 'BCI-778812',
          acceptance_state: 'assigned',
          owner_name: 'Ali',
          assigned_at: new Date(Date.now() - 50 * 3_600_000)
            .toISOString()
            .replace('Z', ''),
        }),
      ],
      pagination: { total: 1, page: 1, limit: 200 },
    });

    renderClient();

    expect(
      await screen.findByText(/Told us: Veritas Architects Sdn Bhd · BCI · BCI-778812/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Buyer: not known yet/)).toBeInTheDocument();
    expect(screen.getByText('Awaiting acceptance by Ali')).toBeInTheDocument();
    expect(screen.getByText('Waiting 2 days')).toBeInTheDocument();
  });

  it('reports a load failure rather than looking empty', async () => {
    listLeads.mockRejectedValue(new Error('Backend is down'));

    renderClient();

    expect(await screen.findByText('Backend is down')).toBeInTheDocument();
  });
});
