/** AFTER-SALES-P1 round 4 (R4-1): one value per field; the subtitle is the complaint number only. */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
let permitted = true;
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/after-sales/service-jobs/j-1',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: any) => <a href={typeof href === 'string' ? href : '#'} {...rest}>{children}</a>,
}));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => permitted }));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/components/common/RecordNavigation', () => ({ default: () => null, RecordNavigation: () => null }));
vi.mock('@/components/audit/AuditTrail', () => ({ default: () => null }));

const useServiceJob = vi.fn();
const noop = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false };
vi.mock('../hooks/useServiceJobs', () => ({
  useServiceJob: (...a: unknown[]) => useServiceJob(...a),
  useServiceJobActions: () => ({ confirm: noop, assign: noop, transition: noop }),
  useServiceJobMutations: () => ({ create: noop, update: noop }),
}));

import ServiceJobDetail from './ServiceJobDetail';

const job = (over: Record<string, unknown> = {}) => ({
  id: 'j-1', job_number: 'SV26/11-0001', complaint_id: 'c-1', complaint_number: 'CMP2026-0101',
  customer_name: 'Ms Lim Trading', contact_name: 'Ms Lim', contact_phone: '+60123456789',
  contact_phone_display: '012-345 6789', city: 'Ipoh', problem: 'Basin leaks',
  status: 'proposed', status_label: 'Proposed',
  technician_id: null, technician_name: null, scheduled_from: null, scheduled_to: null, customer_agreed_by: null,
  ...over,
});

function renderDetail() {
  render(<QueryClientProvider client={new QueryClient()}><ServiceJobDetail jobId="j-1" /></QueryClientProvider>);
}

describe('ServiceJobDetail fields (one value per field)', () => {
  it('the subtitle is the customer alone, no joined values', () => {
    useServiceJob.mockReturnValue({ data: job(), isLoading: false });
    renderDetail();
    expect(document.body.textContent).not.toContain('·');
  });

  it('shows the Customer card: customer, contact on site, phone in local format, problem', () => {
    useServiceJob.mockReturnValue({ data: job(), isLoading: false });
    renderDetail();
    expect(screen.getByText('Contact on site')).toBeInTheDocument();
    expect(screen.getByText('Ms Lim')).toBeInTheDocument();
    expect(screen.getByText('012-345 6789')).toBeInTheDocument();
    expect(screen.getByText('Basin leaks')).toBeInTheDocument();
  });

  it('links the related complaint when the user may view complaints', () => {
    permitted = true;
    useServiceJob.mockReturnValue({ data: job(), isLoading: false });
    renderDetail();
    expect(screen.getByRole('link', { name: 'CMP2026-0101' })).toHaveAttribute('href', '/complaint-management/complaints/c-1');
  });

  it('shows the related complaint number as plain text when the user may not view complaints', () => {
    permitted = false;
    useServiceJob.mockReturnValue({ data: job(), isLoading: false });
    renderDetail();
    expect(screen.getByText('CMP2026-0101')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'CMP2026-0101' })).toBeNull();
    permitted = true;
  });

  it('shows a dash for a job with no related complaint', () => {
    useServiceJob.mockReturnValue({ data: job({ complaint_id: null, complaint_number: null }), isLoading: false });
    renderDetail();
    expect(screen.getAllByText('-').length).toBeGreaterThan(0);
  });
});
