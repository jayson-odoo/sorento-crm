/**
 * AFTER-SALES-P2 red tests (UAC F1, P2, P3): the Products and Warranty cards sit on the job page's Details tab,
 * under Customer, Site and Visit, Products first.
 *
 * Extends `./ServiceJobDetail`: it renders `<ServiceJobProductsCard jobId canEdit />` (canEdit = the dispatch
 * permission `after_sales.service_jobs.dispatch`) and `<ServiceJobWarrantyCard warranty={job.warranty ?? []} />`.
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
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/after-sales/service-jobs/j-1',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: Omit<import('react').ComponentProps<'a'>, 'href'> & { href?: unknown }) => <a href={typeof href === 'string' ? href : '#'} {...rest}>{children}</a>,
}));
let canDispatch = true;
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: (slug: string) => (slug.endsWith('.dispatch') ? canDispatch : true) }));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/components/common/RecordNavigation', () => ({ default: () => null, RecordNavigation: () => null }));
vi.mock('@/components/audit/AuditTrail', () => ({ default: () => null }));
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: () => ({ run: vi.fn(), targetId: null, isPending: false, countdown: null }),
  useRowPending: () => () => false,
}));

const useServiceJob = vi.fn();
const noop = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false };
vi.mock('../hooks/useServiceJobs', () => ({
  useServiceJob: (...a: unknown[]) => useServiceJob(...a),
  useServiceJobActions: () => ({ confirm: noop, assign: noop, transition: noop }),
  useServiceJobMutations: () => ({ create: noop, update: noop }),
  useTechniciansSelect: () => ({ data: [] }),
}));
vi.mock('../hooks/useServiceJobProducts', () => ({
  useServiceJobProducts: () => ({
    data: [{ id: 'l-1', product_id: 'p-1', product_code: 'DEMO-WC-02', product_name: 'Demo water closet', kind_id: 'k-1', kind_name: 'Water Closet', purchase_date: '2020-03-15', defect_type_id: null, defect_label: null, sort_order: 0 }],
    isLoading: false, isError: false, refetch: vi.fn(),
  }),
  useServiceJobProductMutations: () => ({ add: noop, update: noop }),
}));

import ServiceJobDetail from './ServiceJobDetail';

const JOB = {
  id: 'j-1', job_number: 'SV26/11-0001', complaint_id: null, complaint_number: null, customer_name: 'Ms Lim Trading',
  status: 'proposed', status_label: 'Proposed', technician_id: null, technician_name: null,
  scheduled_from: null, scheduled_to: null, customer_agreed_by: null,
  warranty: [{
    id: 'l-1', product_code: 'DEMO-WC-02', product_name: 'Demo water closet', kind_name: 'Water Closet',
    purchase_date: '2020-03-15', defect_label: null,
    verdicts: [{ part_name: 'Ceramic Body', verdict: 'covered', expiry: '2030-03-15', reason: 'Covered', is_lifetime: false, installation_included: false, policy_version: 'v15' }],
  }],
};

function renderDetail() {
  return render(<QueryClientProvider client={new QueryClient()}><ServiceJobDetail jobId="j-1" /></QueryClientProvider>);
}

beforeEach(() => { canDispatch = true; useServiceJob.mockReturnValue({ data: JOB, isLoading: false }); });

describe('ServiceJobDetail warranty cards', () => {
  it('shows Products then Warranty after Customer, Site and Visit', () => {
    renderDetail();
    const titles = ['Customer', 'Site', 'Visit', 'Products', 'Warranty'].map((t) => screen.getByText(t, { selector: '[data-slot="card-title"]' }));
    for (let i = 0; i < titles.length - 1; i += 1) {
      expect(titles[i].compareDocumentPosition(titles[i + 1]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
  });

  it('the Warranty card shows the job warranty answer and its Until date', () => {
    renderDetail();
    expect(screen.getByText('Covered')).toBeInTheDocument();
    expect(screen.getByText('15/03/2030')).toBeInTheDocument();
  });

  it('Add product is offered with dispatch and hidden without it', () => {
    renderDetail();
    expect(screen.getByRole('button', { name: 'Add product' })).toBeInTheDocument();
  });

  it('a viewer without dispatch sees the cards but no Add product', () => {
    canDispatch = false;
    renderDetail();
    expect(screen.getByText('DEMO-WC-02', { selector: 'td *, td' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Add product' })).toBeNull();
  });

  it('a job without a warranty field still renders (older payload)', () => {
    useServiceJob.mockReturnValue({ data: { ...JOB, warranty: undefined }, isLoading: false });
    renderDetail();
    expect(screen.getByText('Warranty', { selector: '[data-slot="card-title"]' })).toBeInTheDocument();
  });
});
