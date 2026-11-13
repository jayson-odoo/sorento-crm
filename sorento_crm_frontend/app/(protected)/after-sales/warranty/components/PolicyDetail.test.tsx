/**
 * AFTER-SALES-P2 red tests (UAC F3): the policy page `/after-sales/warranty/policies/[id]`.
 *
 * Modules the coder builds: `.../warranty/policies/[id]/page.tsx` (thin server page, like P1's job page) rendering
 * `./PolicyDetail` default export, props { policyId: string }. Reads `../hooks/useWarrantyConfig`:
 *   usePolicy(id) -> { data: Policy | undefined, isLoading, isError }
 *   usePolicyTerms(id) -> { data: Term[] | undefined, isLoading, isError }
 *     Term = { id, policy_id, kind_id, part_name, duration_months, is_lifetime, covered_defect_type_ids: string[] | null,
 *              installation_included, qualifications, exclusions }
 *   useKindOptions() -> { data: { id, name }[] };  useDefectOptions() -> { data: { id, label }[] }
 * Header: version + status pill, ONE main button "Supersede" (only while the policy is in force), record pager.
 * Line tabs Details / Terms / History, landing on Terms. Terms are grouped by kind (kind name as a heading), one line
 * per term: Part, Cover ("Lifetime" / "5 years" / "1 year"), Defects ("All defects" or the names), Installation
 * ("Included" / "Excluded"). Details: In force from / In force to (dd/mm/yyyy) and the policy text. History: `AuditTrail`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, fireEvent, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/after-sales/warranty',
  useSearchParams: () => new URLSearchParams(window.location.search),
}));
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: Omit<import('react').ComponentProps<'a'>, 'href'> & { href?: unknown }) => (
    <a href={typeof href === 'string' ? href : '#'} {...rest}>{children}</a>
  ),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
/** One `run` per actionKey, so a test can tell Archive from Delete. */
const runs: Record<string, ReturnType<typeof vi.fn>> = {};
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: (input: { actionKey: string }) => {
    runs[input.actionKey] ??= vi.fn();
    return { run: runs[input.actionKey], targetId: null, isPending: false, countdown: null };
  },
  useRowPending: () => () => false,
}));
vi.mock('@/components/common/RecordNavigation', () => ({ default: () => <div data-testid="record-nav" />, RecordNavigation: () => <div data-testid="record-nav" /> }));
vi.mock('@/components/audit/AuditTrail', () => ({ default: () => <div data-testid="audit-trail" /> }));
vi.mock('./SupersedeDialog', () => ({ SupersedeDialog: ({ open, policy }: { open: boolean; policy: { version: string } }) => (open ? <div role="dialog">Supersede {policy.version}</div> : null) }));

const usePolicy = vi.fn();
const usePolicyTerms = vi.fn();
vi.mock('../hooks/useWarrantyConfig', () => ({
  usePolicy: (...a: unknown[]) => usePolicy(...a),
  usePolicyTerms: (...a: unknown[]) => usePolicyTerms(...a),
  useKindOptions: () => ({ data: [{ id: 'k-1', name: 'Water Closet' }, { id: 'k-2', name: 'Mirror Cabinet' }] }),
  useDefectOptions: () => ({ data: [{ id: 'd-1', label: 'Crack line' }, { id: 'd-2', label: 'Leakage' }] }),
}));

import PolicyDetail from './PolicyDetail';

const POLICY = { id: 'pol-15', version: 'v15', effective_from: '2000-01-01', effective_to: null, policy_text: 'Version 15. Warranty policy.', term_count: 3, created_at: '2000-01-01T00:00:00', updated_at: null };
const term = (over: Record<string, unknown>) => ({ id: 't', policy_id: 'pol-15', kind_id: 'k-1', part_name: 'Ceramic Body', duration_months: null, is_lifetime: true, covered_defect_type_ids: ['d-1', 'd-2'], installation_included: true, qualifications: null, exclusions: null, ...over });
const TERMS = [
  term({ id: 't-1' }),
  term({ id: 't-2', part_name: 'Flushing Fittings', is_lifetime: false, duration_months: 60, covered_defect_type_ids: null, installation_included: false }),
  term({ id: 't-3', kind_id: 'k-2', part_name: 'Mirror Glass', is_lifetime: false, duration_months: 12, covered_defect_type_ids: null }),
];

const renderPage = () => render(<QueryClientProvider client={new QueryClient()}><PolicyDetail policyId="pol-15" /></QueryClientProvider>);

beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState({}, '', '/after-sales/warranty/policies/pol-15');
  usePolicy.mockReturnValue({ data: POLICY, isLoading: false, isError: false });
  usePolicyTerms.mockReturnValue({ data: TERMS, isLoading: false, isError: false });
});

describe('PolicyDetail', () => {
  it('header shows the version, an In force pill and one main button, Supersede', () => {
    renderPage();
    expect(screen.getAllByText('v15').length).toBeGreaterThan(0);
    expect(screen.getByText('In force').closest('[data-slot="badge"]')).not.toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Supersede' }));
    expect(screen.getByRole('dialog')).toHaveTextContent('Supersede v15');
  });

  it('a policy that is no longer in force has no Supersede button', () => {
    usePolicy.mockReturnValue({ data: { ...POLICY, effective_to: '2020-12-31' }, isLoading: false, isError: false });
    renderPage();
    expect(screen.getByText('Superseded')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Supersede' })).toBeNull();
  });

  it('has the three line tabs in order and lands on Terms', () => {
    renderPage();
    expect(screen.getAllByRole('tab').map((t) => (t.textContent || '').replace(/\d+$/, '').trim())).toEqual(['Details', 'Terms', 'History']);
    expect(screen.getByRole('tab', { name: /Terms/ })).toHaveAttribute('aria-selected', 'true');
  });

  it('Terms are grouped by kind, one line per term, with the agreed wording', () => {
    renderPage();
    expect(screen.getByText('Water Closet')).toBeInTheDocument();
    expect(screen.getByText('Mirror Cabinet')).toBeInTheDocument();
    const body = within(screen.getByText('Ceramic Body').closest('tr')!);
    expect(body.getByText('Lifetime')).toBeInTheDocument();
    expect(body.getByText('Crack line, Leakage')).toBeInTheDocument();
    expect(body.getByText('Included')).toBeInTheDocument();
    const fittings = within(screen.getByText('Flushing Fittings').closest('tr')!);
    expect(fittings.getByText('5 years')).toBeInTheDocument();
    expect(fittings.getByText('All defects')).toBeInTheDocument();
    expect(fittings.getByText('Excluded')).toBeInTheDocument();
    expect(within(screen.getByText('Mirror Glass').closest('tr')!).getByText('1 year')).toBeInTheDocument();
  });

  it('Details shows the period as dd/mm/yyyy and the policy text', async () => {
    renderPage();
    await userEvent.click(screen.getByRole('tab', { name: 'Details' }));
    expect(screen.getByText('01/01/2000')).toBeInTheDocument();
    expect(screen.getByText('Version 15. Warranty policy.')).toBeInTheDocument();
    expect(screen.queryByText(/pol-15/)).toBeNull();
  });

  it('History shows the audit trail', async () => {
    renderPage();
    await userEvent.click(screen.getByRole('tab', { name: 'History' }));
    expect(screen.getByTestId('audit-trail')).toBeInTheDocument();
  });

  it('a policy with no terms shows an empty state with no button', () => {
    usePolicyTerms.mockReturnValue({ data: [], isLoading: false, isError: false });
    renderPage();
    const heading = screen.getByRole('heading', { name: /no terms/i });
    expect(within(heading.parentElement as HTMLElement).queryByRole('button')).toBeNull();
  });

  it('shows a skeleton while loading', () => {
    usePolicy.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    const { container } = renderPage();
    expect(container.querySelector('[data-slot="skeleton"]')).not.toBeNull();
  });
});
