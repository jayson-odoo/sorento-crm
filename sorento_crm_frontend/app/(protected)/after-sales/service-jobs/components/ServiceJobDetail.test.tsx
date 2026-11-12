/**
 * AFTER-SALES-P1 red tests (UAC D3, D5): the job page header.
 *
 * Contract: `./ServiceJobDetail` default export, props `{ jobId: string }`.
 * It reads `useServiceJob(id)` and `useServiceJobActions()` from `../hooks/useServiceJobs`.
 *   useServiceJob -> { data: ServiceJob | undefined, isLoading, isError }
 *   useServiceJobActions -> { confirm, assign, transition } each { mutate, mutateAsync, isPending }
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/after-sales/service-jobs/j-1',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: Omit<import('react').ComponentProps<'a'>, 'href'> & { href?: unknown }) => (
    <a href={typeof href === 'string' ? href : '#'} {...rest}>{children}</a>
  ),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/components/common/RecordNavigation', () => ({
  default: () => <div data-testid="record-nav" />,
  RecordNavigation: () => <div data-testid="record-nav" />,
}));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('@/components/audit/AuditTrail', () => ({ default: () => <div data-testid="audit-trail" /> }));

const useServiceJob = vi.fn();
const noop = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false };
vi.mock('../hooks/useServiceJobs', () => ({
  useServiceJob: (...a: unknown[]) => useServiceJob(...a),
  useServiceJobActions: () => ({ confirm: noop, assign: noop, transition: noop }),
  useServiceJobMutations: () => ({ create: noop, update: noop }),
  useServiceJobMutations: () => ({ create: noop, update: noop }),
}));

import ServiceJobDetail from './ServiceJobDetail';

const STEP_LABELS = ['Confirm date', 'Assign technician', 'On the way', 'Arrived', 'Complete', 'Verify'];

function job(over: Record<string, unknown> = {}) {
  return {
    id: 'j-1', job_number: 'SV26/11-0001', complaint_id: 'c-1', complaint_number: 'CMP-0001',
    customer_name: 'Ms Lim Trading', city: 'Subang Jaya', status: 'proposed', status_label: 'Proposed',
    technician_id: null, technician_name: null, scheduled_from: null, scheduled_to: null,
    customer_agreed_by: null, ...over,
  };
}

function renderDetail() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={client}>
      <ServiceJobDetail jobId="j-1" />
    </QueryClientProvider>,
  );
}

function stepButtons() {
  return STEP_LABELS.flatMap((l) => screen.queryAllByRole('button', { name: l }));
}

beforeEach(() => useServiceJob.mockReset());

describe('ServiceJobDetail header (D3)', () => {
  it.each([
    ['proposed', null, 'Confirm date'],
    ['confirmed', null, 'Assign technician'],
    ['confirmed', 'tech-1', 'On the way'],
    ['on_the_way', 'tech-1', 'Arrived'],
    ['arrived', 'tech-1', 'Complete'],
    ['completed', 'tech-1', 'Verify'],
  ])('%s (technician %s) shows exactly one next-step button: %s', (status, technician_id, label) => {
    useServiceJob.mockReturnValue({
      data: job({ status, technician_id, technician_name: technician_id ? 'Ali' : null }),
      isLoading: false,
    });
    renderDetail();
    const buttons = stepButtons();
    expect(buttons).toHaveLength(1);
    expect(buttons[0]).toHaveAccessibleName(label);
  });

  it.each(['verified', 'cancelled'])('%s shows no next-step button', (status) => {
    useServiceJob.mockReturnValue({ data: job({ status }), isLoading: false });
    renderDetail();
    expect(stepButtons()).toHaveLength(0);
  });

  it('shows job number, the customer as the subtitle, and no uuid', () => {
    useServiceJob.mockReturnValue({ data: job(), isLoading: false });
    renderDetail();
    expect(screen.getByText('SV26/11-0001')).toBeInTheDocument();
    expect(screen.getAllByText('Ms Lim Trading').length).toBeGreaterThan(0);
    expect(screen.queryByText(/j-1|c-1/)).not.toBeInTheDocument();
  });

  it('has the Details and History tabs (D5)', () => {
    useServiceJob.mockReturnValue({ data: job(), isLoading: false });
    renderDetail();
    expect(screen.getByRole('tab', { name: 'Details' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'History' })).toBeInTheDocument();
  });

  it('shows "-" for unknown values (D5)', () => {
    useServiceJob.mockReturnValue({ data: job(), isLoading: false });
    renderDetail();
    expect(screen.getAllByText('-').length).toBeGreaterThan(0);
  });

  it('shows a loading state without crashing', () => {
    useServiceJob.mockReturnValue({ data: undefined, isLoading: true });
    renderDetail();
    expect(stepButtons()).toHaveLength(0);
  });
});
