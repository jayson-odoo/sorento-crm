/**
 * The list exists because the board is a day.
 *
 * A job starts Proposed with no date, so it is on no day and appeared on no board; a job
 * confirmed for last Tuesday leaves the board as soon as it moves on. Both read as "the
 * job disappeared" - which is exactly what happened to somebody who raised one, proposed
 * a date, assigned a technician, and then could not find it again.
 *
 * So the two things worth asserting are that an undated job appears at all, and that it
 * says why it has no date rather than showing a blank cell that reads as missing data.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ServiceJobsList from './ServiceJobsList';
import type { ServiceJob } from '../services/serviceJobService';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  usePathname: () => '/complaint-management/service-jobs',
}));

// DataGrid persists column preferences through this hook, which fires a request.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const listServiceJobs = vi.fn();

vi.mock('../services/serviceJobService', async () => {
  const actual =
    await vi.importActual<typeof import('../services/serviceJobService')>(
      '../services/serviceJobService',
    );
  return { ...actual, listServiceJobs: (...args: unknown[]) => listServiceJobs(...args) };
});

function job(overrides: Partial<ServiceJob> = {}): ServiceJob {
  return {
    id: 'j1',
    job_number: 'SV26/08-0005',
    source_entity_type: 'complaint',
    source_entity_id: 'c1',
    status_key: 'proposed',
    site_address: '2 Jalan SL 16/1, Kajang',
    site_contact_name: null,
    site_contact_phone: null,
    site_latitude: null,
    site_longitude: null,
    site_place_id: null,
    scheduled_from: null,
    scheduled_to: null,
    proposed_at: null,
    confirmed_at: null,
    customer_agreed_by: null,
    arrived_at: null,
    completed_at: null,
    verified_at: null,
    diagnosis_root_cause_id: null,
    charge_state: null,
    charge_amount: null,
    waiting_on_party: null,
    waiting_on_reason: null,
    waiting_since: null,
    attend_seconds: null,
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ServiceJobsList />
    </QueryClientProvider>,
  );
}

describe('service jobs list', () => {
  it('lists a job that has no date, which no dispatch board could show', async () => {
    listServiceJobs.mockResolvedValue({
      data: [job()],
      pagination: { total: 1, page: 1, limit: 100 },
      empty: false,
    });
    renderList();
    expect(await screen.findByText('SV26/08-0005')).toBeInTheDocument();
  });

  it('says the job is not scheduled rather than leaving the cell blank', async () => {
    // Blank reads as missing data. "Not scheduled" is the actual state, and the commonest
    // one: nobody has agreed a time yet, which is what Proposed means.
    listServiceJobs.mockResolvedValue({
      data: [job()],
      pagination: { total: 1, page: 1, limit: 100 },
      empty: false,
    });
    renderList();
    expect(await screen.findByText('Not scheduled')).toBeInTheDocument();
  });

  it('opens the job on its own page when a row is clicked', async () => {
    // The whole point: a job has an address of its own, reachable without knowing its day.
    listServiceJobs.mockResolvedValue({
      data: [job()],
      pagination: { total: 1, page: 1, limit: 100 },
      empty: false,
    });
    renderList();
    (await screen.findByText('SV26/08-0005')).click();
    await waitFor(() =>
      expect(push).toHaveBeenCalledWith('/complaint-management/service-jobs/j1'),
    );
  });

  it('offers the board rather than an Add button', async () => {
    // Jobs are raised FROM a case, never here - a job copies the site that case reported,
    // so an Add button would open a form with nothing to copy.
    listServiceJobs.mockResolvedValue({
      data: [],
      pagination: { total: 0, page: 1, limit: 100 },
      empty: true,
    });
    renderList();
    const board = await screen.findByRole('button', { name: /Dispatch board/i });
    board.click();
    await waitFor(() =>
      expect(push).toHaveBeenCalledWith('/complaint-management/service-jobs/board'),
    );
    expect(screen.queryByRole('button', { name: /^Add/i })).toBeNull();
  });
});
