/**
 * The job panel - AC-F5 as the user meets it, plus the one destructive-ish action.
 *
 * **The backend's refusal must reach the dispatcher verbatim.** `confirm_job` returns a 422
 * naming which half is missing - the date or the agreement - and that sentence is the only
 * useful thing to say. Replacing it with "Something went wrong" is the single most likely way
 * this screen gets worse, because it looks like defensive coding.
 *
 * **Rejecting a visit is behind a confirmation.** It is not a delete, but it un-agrees a date
 * with a customer and marks the case as waiting on them. A one-click version gets pressed by
 * accident on a trackpad, and the resulting record says a consumer cancelled when they did
 * not.
 *
 * The panel also must not offer a move the graph forbids: a completed job has no "Confirm
 * date" section, and a proposed one has no "Arrived" button. The server refuses either way,
 * so this is about not inviting a 422.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { ServiceJobPanel } from './components/ServiceJobPanel';
import type { ServiceJob, ServiceJobStatusKey } from './services/serviceJobService';

const confirmServiceJob = vi.fn();
const rejectServiceJobVisit = vi.fn();
const toastError = vi.fn();
const toastSuccess = vi.fn();

vi.mock('./services/serviceJobService', async () => {
  const actual = await vi.importActual<typeof import('./services/serviceJobService')>(
    './services/serviceJobService',
  );
  return {
    ...actual,
    confirmServiceJob: (...args: unknown[]) => confirmServiceJob(...args),
    rejectServiceJobVisit: (...args: unknown[]) => rejectServiceJobVisit(...args),
    assignServiceJob: vi.fn(),
    startServiceJobTravel: vi.fn(),
    arriveAtServiceJob: vi.fn(),
    completeServiceJob: vi.fn(),
    verifyServiceJob: vi.fn(),
  };
});

vi.mock('sonner', () => ({
  toast: {
    error: (...args: unknown[]) => toastError(...args),
    success: (...args: unknown[]) => toastSuccess(...args),
  },
}));

function job(status: ServiceJobStatusKey, overrides: Partial<ServiceJob> = {}): ServiceJob {
  return {
    id: 'j1',
    job_number: 'SV26/08-0001',
    source_entity_type: 'complaint',
    source_entity_id: 'c1',
    status_key: status,
    site_address: '12 Jalan Damai, Shah Alam',
    site_contact_name: 'Puan Aminah',
    site_contact_phone: '+60127770099',
    site_latitude: null,
    site_longitude: null,
    site_place_id: null,
    scheduled_from: null,
    scheduled_to: null,
    proposed_at: '2026-08-04T01:00:00',
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
    created_at: '2026-08-04T01:00:00',
    updated_at: null,
    ...overrides,
  };
}

function renderPanel(target: ServiceJob) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ServiceJobPanel job={target} technicians={[]} open onOpenChange={() => {}} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('service job panel', () => {
  it('offers the confirm section on a proposed job', () => {
    renderPanel(job('proposed'));
    expect(screen.getByText('Confirm the visit')).toBeInTheDocument();
    // A date alone is explicitly not enough, and the panel says so before anybody tries.
    expect(screen.getByText(/A date alone is not a confirmation/i)).toBeInTheDocument();
  });

  it('does not offer an arrival on a proposed job', () => {
    renderPanel(job('proposed'));
    expect(screen.queryByRole('button', { name: 'Arrived' })).not.toBeInTheDocument();
  });

  it('does not offer a confirm on a completed job', () => {
    renderPanel(job('completed'));
    expect(screen.queryByText('Confirm the visit')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Verify' })).toBeInTheDocument();
  });

  it("surfaces the backend's own refusal rather than a generic message", async () => {
    confirmServiceJob.mockRejectedValue(
      new Error(
        "A service job cannot be confirmed without a date. 'Service Date: TBA' is a proposed job, not a confirmed one.",
      ),
    );
    renderPanel(job('proposed'));

    fireEvent.change(screen.getByLabelText('Agreed by'), {
      target: { value: 'Consumer agreed' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm date' }));

    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith(expect.stringContaining('Service Date: TBA')),
    );
  });

  it('sends both halves when the dispatcher supplies them', async () => {
    confirmServiceJob.mockResolvedValue(job('confirmed'));
    renderPanel(job('proposed'));

    fireEvent.change(screen.getByLabelText('Date and time'), {
      target: { value: '2026-08-10T10:00' },
    });
    fireEvent.change(screen.getByLabelText('Agreed by'), {
      target: { value: 'Consumer agreed on WhatsApp' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm date' }));

    await waitFor(() => expect(confirmServiceJob).toHaveBeenCalled());
    const [, payload] = confirmServiceJob.mock.calls[0] as [string, Record<string, unknown>];
    expect(payload.customer_agreed_by).toBe('Consumer agreed on WhatsApp');
    expect(payload.scheduled_from).toBeTruthy();
  });

  it('asks before recording a rejected visit rather than firing on one click', async () => {
    renderPanel(job('confirmed'));

    fireEvent.click(screen.getByRole('button', { name: 'Customer rejected' }));

    await waitFor(() =>
      expect(screen.getByText('Record a rejected visit')).toBeInTheDocument(),
    );
    // Nothing has been sent yet - the dialog is the gate.
    expect(rejectServiceJobVisit).not.toHaveBeenCalled();
  });

  it('names who is waited on once a visit has been rejected', () => {
    renderPanel(
      job('proposed', {
        waiting_on_party: 'customer',
        waiting_on_reason: 'awaiting_visit_date',
        waiting_since: '2026-08-04T02:00:00',
      }),
    );
    expect(screen.getByText(/customer \(awaiting visit date\)/i)).toBeInTheDocument();
  });

  it('reads an unarrived job as "Not arrived" rather than zero', () => {
    renderPanel(job('confirmed'));
    expect(screen.getByText('Not arrived')).toBeInTheDocument();
  });
});
