/**
 * The complaint -> service job door.
 *
 * **The section renders empty.** This is the CRUD standard's "always render every section",
 * and here it earns its keep: a complaint with no service job is the ordinary state of every
 * complaint, so a section that only appeared once a job existed would never be discovered by
 * the person who needs to raise the first one.
 *
 * **Raising asks first, and the question changes when jobs already exist.** A second job is a
 * revisit, which is legitimate and also a number somebody reports on - so the dialog says so
 * rather than silently adding one.
 *
 * **The request carries the case id and nothing else.** The Site is read off the case
 * server-side (AC-B3). If this ever starts posting an address, a van eventually goes to a
 * dealer's shop instead of a house, and both are real addresses so nothing looks wrong.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ComplaintServiceJobsSection from './ComplaintServiceJobsSection';
import type { ServiceJob } from '../../service-jobs/services/serviceJobService';

const getJobsForSource = vi.fn();
const raiseServiceJobFromSource = vi.fn();
const toastError = vi.fn();
const toastSuccess = vi.fn();

vi.mock('../../service-jobs/services/serviceJobService', async () => {
  const actual = await vi.importActual<
    typeof import('../../service-jobs/services/serviceJobService')
  >('../../service-jobs/services/serviceJobService');
  return {
    ...actual,
    getJobsForSource: (...args: unknown[]) => getJobsForSource(...args),
    raiseServiceJobFromSource: (...args: unknown[]) => raiseServiceJobFromSource(...args),
  };
});

vi.mock('sonner', () => ({
  toast: {
    error: (...args: unknown[]) => toastError(...args),
    success: (...args: unknown[]) => toastSuccess(...args),
  },
}));

function job(overrides: Partial<ServiceJob> = {}): ServiceJob {
  return {
    id: 'j1',
    job_number: 'SV26/08-0009',
    source_entity_type: 'complaint',
    source_entity_id: 'c1',
    status_key: 'proposed',
    site_address: '12 Jalan Damai, Shah Alam',
    site_contact_name: 'Puan Aminah',
    site_contact_phone: '+60127770099',
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

function renderSection() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ComplaintServiceJobsSection complaintId="c1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('complaint service jobs section', () => {
  it('renders with a next step when the complaint has no job', async () => {
    getJobsForSource.mockResolvedValue([]);
    renderSection();

    await waitFor(() =>
      expect(screen.getByText(/No service job yet/i)).toBeInTheDocument(),
    );
    expect(screen.getByRole('button', { name: 'Raise service job' })).toBeInTheDocument();
  });

  it('lists an existing job with its status', async () => {
    getJobsForSource.mockResolvedValue([job()]);
    renderSection();

    await waitFor(() => expect(screen.getByText('SV26/08-0009')).toBeInTheDocument());
    expect(screen.getByText('Proposed')).toBeInTheDocument();
    expect(screen.getByText('12 Jalan Damai, Shah Alam')).toBeInTheDocument();
  });

  it('asks before raising rather than firing on one click', async () => {
    getJobsForSource.mockResolvedValue([]);
    renderSection();

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Raise service job' })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Raise service job' }));

    await waitFor(() =>
      expect(screen.getByText('Raise a service job?')).toBeInTheDocument(),
    );
    expect(raiseServiceJobFromSource).not.toHaveBeenCalled();
  });

  it('says a second job is a separate visit when one already exists', async () => {
    getJobsForSource.mockResolvedValue([job()]);
    renderSection();

    await waitFor(() => expect(screen.getByText('SV26/08-0009')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Raise service job' }));

    await waitFor(() =>
      expect(screen.getByText(/already has 1 service job/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/separate visit/i)).toBeInTheDocument();
  });

  it('sends only the case identity, never an address', async () => {
    getJobsForSource.mockResolvedValue([]);
    raiseServiceJobFromSource.mockResolvedValue(job());
    renderSection();

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Raise service job' })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Raise service job' }));
    await waitFor(() => screen.getByText('Raise a service job?'));
    fireEvent.click(screen.getByRole('button', { name: 'Raise job' }));

    await waitFor(() =>
      expect(raiseServiceJobFromSource).toHaveBeenCalledWith('complaint', 'c1'),
    );
    // Exactly two arguments: the source type and the id. Anything more is an address
    // travelling from a screen that may be showing the dealer's shop.
    expect(raiseServiceJobFromSource.mock.calls[0]).toHaveLength(2);
  });

  it('surfaces the backend message when raising fails', async () => {
    getJobsForSource.mockResolvedValue([]);
    raiseServiceJobFromSource.mockRejectedValue(new Error('Permission required: dispatch'));
    renderSection();

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Raise service job' })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Raise service job' }));
    await waitFor(() => screen.getByText('Raise a service job?'));
    fireEvent.click(screen.getByRole('button', { name: 'Raise job' }));

    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith(expect.stringContaining('Permission required')),
    );
  });
});
