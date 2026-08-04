/**
 * The dispatch board - the three things this screen must not get wrong.
 *
 * 1. **The unassigned column always renders.** A confirmed job nobody is going to is the most
 *    important thing on the board, and a board that only draws technician columns groups it
 *    out of existence. That failure is invisible in a happy-path screenshot, because with any
 *    assigned work present the screen still looks correct.
 *
 * 2. **A stall reports its elapsed time.** AC-F4's whole point is that the drift is stated
 *    rather than left to be noticed. A stall list without the duration is a list of jobs.
 *
 * 3. **An empty stall list is a sentence, not a blank.** "No stalled jobs" tells a dispatcher
 *    the check ran; an empty div tells them nothing, and the two look identical when the API
 *    fails silently.
 *
 * `formatDuration` is unit-tested alongside because a stall reading "0m" after three days
 * would be read as noise and dismissed, and it is one integer division away from happening.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import DispatchBoardPage from './page';
import { formatDuration, type BoardGroup, type StalledJob } from './services/serviceJobService';

const getDispatchBoard = vi.fn();
const getStalledJobs = vi.fn();
const listTechnicians = vi.fn();
const getServiceJob = vi.fn();

vi.mock('./services/serviceJobService', async () => {
  const actual = await vi.importActual<typeof import('./services/serviceJobService')>(
    './services/serviceJobService',
  );
  return {
    ...actual,
    getDispatchBoard: (...args: unknown[]) => getDispatchBoard(...args),
    getStalledJobs: () => getStalledJobs(),
    listTechnicians: (...args: unknown[]) => listTechnicians(...args),
    getServiceJob: (...args: unknown[]) => getServiceJob(...args),
  };
});

function boardGroup(overrides: Partial<BoardGroup> = {}): BoardGroup {
  return {
    day: '2026-08-04',
    technician_id: 't1',
    technician_name: 'Ah Meng',
    jobs: [
      {
        service_job_id: 'j1',
        job_number: 'SV26/08-0001',
        status_key: 'confirmed',
        scheduled_from: '2026-08-04T10:00:00',
        scheduled_to: null,
        site_address: '12 Jalan Damai, Shah Alam',
        site_contact_name: 'Puan Aminah',
        site_contact_phone: '+60127770099',
        source_entity_type: 'complaint',
        source_entity_id: 'c1',
      },
    ],
    ...overrides,
  };
}

function stall(overrides: Partial<StalledJob> = {}): StalledJob {
  return {
    service_job_id: 'j9',
    job_number: 'SV26/08-0003',
    scheduled_from: '2026-08-01T10:00:00',
    stalled_seconds: 3 * 86400,
    site_address: '5 Lorong Bukit, Klang',
    source_entity_type: 'complaint',
    source_entity_id: 'c9',
    waiting_on_party: null,
    waiting_on_reason: null,
    ...overrides,
  };
}

function renderBoard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <DispatchBoardPage />
    </QueryClientProvider>,
  );
}

describe('dispatch board', () => {
  it('renders the unassigned column even when every job has a technician', async () => {
    getDispatchBoard.mockResolvedValue([boardGroup()]);
    getStalledJobs.mockResolvedValue([]);
    listTechnicians.mockResolvedValue([]);

    renderBoard();

    await waitFor(() => expect(screen.getByText('Unassigned')).toBeInTheDocument());
    expect(screen.getByText('Ah Meng')).toBeInTheDocument();
  });

  it('puts an unassigned confirmed job on the board rather than dropping it', async () => {
    getDispatchBoard.mockResolvedValue([
      boardGroup({ technician_id: null, technician_name: null }),
    ]);
    getStalledJobs.mockResolvedValue([]);
    listTechnicians.mockResolvedValue([]);

    renderBoard();

    await waitFor(() => expect(screen.getByText('SV26/08-0001')).toBeInTheDocument());
    expect(screen.getByText('Unassigned')).toBeInTheDocument();
    // Nobody is working that day, and the board says so with a next step.
    expect(screen.getByText(/Nobody is assigned any work/i)).toBeInTheDocument();
  });

  it('states the elapsed time on a stalled job', async () => {
    getDispatchBoard.mockResolvedValue([]);
    getStalledJobs.mockResolvedValue([stall()]);
    listTechnicians.mockResolvedValue([]);

    renderBoard();

    await waitFor(() => expect(screen.getByText('SV26/08-0003')).toBeInTheDocument());
    expect(screen.getByText(/stalled 3d 0h/)).toBeInTheDocument();
  });

  it('says the stall check ran when nothing is stalled', async () => {
    getDispatchBoard.mockResolvedValue([]);
    getStalledJobs.mockResolvedValue([]);
    listTechnicians.mockResolvedValue([]);

    renderBoard();

    await waitFor(() =>
      expect(screen.getByText(/No stalled jobs/i)).toBeInTheDocument(),
    );
  });

  it('surfaces the backend message when the board fails to load', async () => {
    getDispatchBoard.mockRejectedValue(new Error('Permission required: service_jobs.view'));
    getStalledJobs.mockResolvedValue([]);
    listTechnicians.mockResolvedValue([]);

    renderBoard();

    await waitFor(() =>
      expect(screen.getByText(/Permission required/i)).toBeInTheDocument(),
    );
  });
});

describe('formatDuration', () => {
  it('reads a three-day stall in days, not minutes', () => {
    expect(formatDuration(3 * 86400)).toBe('3d 0h');
  });

  it('reads a two-and-a-half-hour attend time in hours and minutes', () => {
    expect(formatDuration(2.5 * 3600)).toBe('2h 30m');
  });

  it('renders a dash rather than zero for a job nobody has arrived at', () => {
    // Zero would enter an average as a perfect score for a visit that never happened.
    expect(formatDuration(null)).toBe('-');
  });
});
