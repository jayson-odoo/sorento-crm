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
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/complaint-management/service-jobs/j-1',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: any) => <a href={typeof href === 'string' ? href : '#'} {...rest}>{children}</a>,
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/components/common/RecordNavigation', () => ({ default: () => null, RecordNavigation: () => null }));
vi.mock('@/components/audit/AuditTrail', () => ({ default: () => null }));

const useServiceJob = vi.fn();
const noop = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false };
vi.mock('../hooks/useServiceJobs', () => ({
  useServiceJob: (...a: unknown[]) => useServiceJob(...a),
  useServiceJobActions: () => ({ confirm: noop, assign: noop, transition: noop }),
}));

import ServiceJobDetail from './ServiceJobDetail';

const job = (over: Record<string, unknown> = {}) => ({
  id: 'j-1', job_number: 'SV26/11-0001', complaint_id: 'c-1', complaint_number: 'CMP2026-0101',
  customer_name: 'Ms Lim Trading', city: 'Ipoh', status: 'proposed', status_label: 'Proposed',
  technician_id: null, technician_name: null, scheduled_from: null, scheduled_to: null, customer_agreed_by: null,
  ...over,
});

function renderDetail() {
  render(<QueryClientProvider client={new QueryClient()}><ServiceJobDetail jobId="j-1" /></QueryClientProvider>);
}

describe('ServiceJobDetail fields (R4-1)', () => {
  it('subtitle is the complaint number alone, no joined values', () => {
    useServiceJob.mockReturnValue({ data: job(), isLoading: false });
    renderDetail();
    const subtitle = screen.getByText('CMP2026-0101');
    expect(subtitle.textContent).toBe('CMP2026-0101');
    expect(document.body.textContent).not.toContain('·');
  });

  it('shows a dash when the complaint has no number', () => {
    useServiceJob.mockReturnValue({ data: job({ complaint_number: null }), isLoading: false });
    renderDetail();
    expect(screen.getAllByText('-').length).toBeGreaterThan(0);
  });

  it('shows Customer as its own labelled field', () => {
    useServiceJob.mockReturnValue({ data: job(), isLoading: false });
    renderDetail();
    expect(screen.getByText('Customer')).toBeInTheDocument();
    expect(screen.getByText('Ms Lim Trading')).toBeInTheDocument();
  });
});
