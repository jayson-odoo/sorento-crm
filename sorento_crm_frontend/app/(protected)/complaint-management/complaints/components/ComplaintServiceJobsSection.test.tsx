/**
 * AFTER-SALES-P1 red tests (UAC D6): the Service Jobs section on the complaint detail page.
 *
 * Contract: `./ComplaintServiceJobsSection` default export, props { complaintId: string }. Fix round 1 (S-11): raising lives only in the complaint gear, so the
 * section never shows a Raise button.
 * Hooks from `../../service-jobs/hooks/useServiceJobs`:
 *   useComplaintServiceJobs(complaintId) -> { data: ServiceJob[], isLoading }
 *   useRaiseServiceJob() -> { mutate, mutateAsync, isPending }
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';

vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: any) => (
    <a href={typeof href === 'string' ? href : '#'} {...rest}>{children}</a>
  ),
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/complaint-management/complaints/c-1',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

const useComplaintServiceJobs = vi.fn();
vi.mock('../../service-jobs/hooks/useServiceJobs', () => ({
  useComplaintServiceJobs: (...a: unknown[]) => useComplaintServiceJobs(...a),
}));

import ComplaintServiceJobsSection from './ComplaintServiceJobsSection';

const job = (over: Record<string, unknown> = {}) => ({
  id: 'j-1', job_number: 'SV26/11-0001', status: 'confirmed', status_label: 'Confirmed',
  scheduled_from: '2026-11-20T02:00:00', technician_name: 'Ali', ...over,
});

function renderSection(props: Record<string, unknown> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={client}>
      <ComplaintServiceJobsSection complaintId="c-1" {...props} />
    </QueryClientProvider>,
  );
}

beforeEach(() => { useComplaintServiceJobs.mockReset(); });

describe('ComplaintServiceJobsSection (D6)', () => {
  it('lists each job on one line: number link, status pill, scheduled, technician', () => {
    useComplaintServiceJobs.mockReturnValue({ data: [job()], isLoading: false });
    renderSection();
    expect(screen.getByRole('link', { name: 'SV26/11-0001' })).toHaveAttribute(
      'href', '/complaint-management/service-jobs/j-1',
    );
    expect(screen.getByText('Confirmed')).toBeInTheDocument();
    expect(screen.getByText(/20\/11\/2026/)).toBeInTheDocument();
    expect(screen.getByText('Ali')).toBeInTheDocument();
  });

  it.each(['confirmed', 'verified', 'cancelled'])('never shows a Raise button (job is %s)', (status) => {
    useComplaintServiceJobs.mockReturnValue({ data: [job({ status, status_label: status })], isLoading: false });
    renderSection();
    expect(screen.queryByRole('button', { name: 'Raise service job' })).toBeNull();
  });

  it('with no jobs shows a heading and hint and no button (empty state, no CTA)', () => {
    useComplaintServiceJobs.mockReturnValue({ data: [], isLoading: false });
    renderSection();
    expect(screen.getByText('Service Jobs')).toBeInTheDocument();
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('renders a loading state', () => {
    useComplaintServiceJobs.mockReturnValue({ data: undefined, isLoading: true });
    renderSection();
    expect(screen.getByText('Service Jobs')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Raise service job' })).toBeNull();
  });
});
