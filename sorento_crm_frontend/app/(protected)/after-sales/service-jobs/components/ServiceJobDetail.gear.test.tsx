/** AFTER-SALES-P1 fix round 2 (R2-7): "Change technician" in the gear for Proposed or Confirmed jobs that have one. */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
const permitted = true;
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/after-sales/service-jobs/j-1',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: Omit<import('react').ComponentProps<'a'>, 'href'> & { href?: unknown }) => <a href={typeof href === 'string' ? href : '#'} {...rest}>{children}</a>,
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
  useTechniciansSelect: () => ({ data: [{ id: 't-1', name: 'Ali' }] }),
}));

import ServiceJobDetail from './ServiceJobDetail';

const job = (over: Record<string, unknown>) => ({
  id: 'j-1', job_number: 'SV26/11-0001', complaint_id: null, complaint_number: null, customer_name: 'X',
  status: 'confirmed', status_label: 'Confirmed', technician_id: 't-1', technician_name: 'Ali',
  scheduled_from: null, scheduled_to: null, customer_agreed_by: null, ...over,
});

async function openGear() {
  const client = new QueryClient();
  render(<QueryClientProvider client={client}><ServiceJobDetail jobId="j-1" /></QueryClientProvider>);
  const gear = screen.getByRole('button', { name: 'Service job actions' });
  fireEvent.pointerDown(gear, { button: 0, pointerId: 1 });
  fireEvent.pointerUp(gear, { button: 0, pointerId: 1 });
  fireEvent.click(gear);
  await waitFor(() => expect(gear.getAttribute('aria-expanded')).toBe('true'));
}

beforeEach(() => useServiceJob.mockReset());

describe('gear: Change technician', () => {
  it.each(['proposed', 'confirmed'])('is offered on a %s job that has a technician and opens the Assign dialog', async (status) => {
    useServiceJob.mockReturnValue({ data: job({ status }), isLoading: false });
    await openGear();
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Change technician' }));
    expect(await screen.findByRole('dialog')).toHaveTextContent('Assign technician');
  });

  it('is not offered without a technician', async () => {
    useServiceJob.mockReturnValue({ data: job({ technician_id: null, technician_name: null }), isLoading: false });
    await openGear();
    expect(screen.queryByRole('menuitem', { name: 'Change technician' })).toBeNull();
    expect(screen.queryByRole('menuitem', { name: 'Arrived' })).toBeNull();
  });

  it('is not offered once the technician is on the way', async () => {
    useServiceJob.mockReturnValue({ data: job({ status: 'on_the_way' }), isLoading: false });
    await openGear();
    expect(screen.queryByRole('menuitem', { name: 'Change technician' })).toBeNull();
  });
});
