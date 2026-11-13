/**
 * AFTER-SALES-P2 browser re-run: the policy page header's Supersede is admin-only like every other write
 * (`useEffectiveIsSuperadmin` from `@/hooks/useEffectiveIsSuperadmin`): a non-admin sees no Supersede button on an
 * in-force policy, an admin does.
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
  usePathname: () => '/after-sales/warranty/policies/pol-15',
  useSearchParams: () => new URLSearchParams(window.location.search),
}));
vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: Omit<import('react').ComponentProps<'a'>, 'href'> & { href?: unknown }) => (
    <a href={typeof href === 'string' ? href : '#'} {...rest}>{children}</a>
  ),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
let isAdmin = true;
vi.mock('@/hooks/useEffectiveIsSuperadmin', () => ({ useEffectiveIsSuperadmin: () => isAdmin }));
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: () => ({ run: vi.fn(), targetId: null, isPending: false, countdown: null }),
  useRowPending: () => () => false,
}));
vi.mock('@/components/common/RecordNavigation', () => ({ default: () => <div />, RecordNavigation: () => <div /> }));
vi.mock('@/components/audit/AuditTrail', () => ({ default: () => <div /> }));
vi.mock('./SupersedeDialog', () => ({ SupersedeDialog: () => null }));
vi.mock('./TermFormDialog', () => ({ TermFormDialog: () => null }));
vi.mock('../hooks/useWarrantyConfig', () => ({
  usePolicy: () => ({ data: { id: 'pol-15', version: 'v15', effective_from: '2000-01-01', effective_to: null, policy_text: null, term_count: 0, created_at: '2000-01-01T00:00:00', updated_at: null }, isLoading: false, isError: false }),
  usePolicyTerms: () => ({ data: [], isLoading: false, isError: false }),
  useKindOptions: () => ({ data: [] }),
  useDefectOptions: () => ({ data: [] }),
}));

import PolicyDetail from './PolicyDetail';

const renderPage = () => render(<QueryClientProvider client={new QueryClient()}><PolicyDetail policyId="pol-15" /></QueryClientProvider>);

beforeEach(() => { isAdmin = true; window.history.replaceState(null, '', '/after-sales/warranty/policies/pol-15'); });

describe('PolicyDetail Supersede is admin-only', () => {
  it('an admin sees Supersede on an in-force policy', () => {
    renderPage();
    expect(screen.getByRole('button', { name: 'Supersede' })).toBeInTheDocument();
  });

  it('a non-admin sees no Supersede button', () => {
    isAdmin = false;
    renderPage();
    expect(screen.getByText('In force')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Supersede' })).toBeNull();
  });
});
