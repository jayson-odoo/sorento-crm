/**
 * AFTER-SALES-P2 review round (item 10): one filled main button per page. On the policy page the header's Supersede is
 * the page's filled button, so the Terms tab's Create is an OUTLINE button (the repo's Button `variant="outline"`:
 * `border-input`, never `bg-primary`).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, fireEvent, within } from '@testing-library/react';

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
let isAdmin = true;
vi.mock('@/hooks/useEffectiveIsSuperadmin', () => ({ useEffectiveIsSuperadmin: () => isAdmin }));
const runs: Record<string, ReturnType<typeof vi.fn>> = {};
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: (input: { actionKey: string }) => {
    runs[input.actionKey] ??= vi.fn();
    return { run: runs[input.actionKey], targetId: null, isPending: false, countdown: null };
  },
  useRowPending: () => () => false,
}));
const { mut } = vi.hoisted(() => ({ mut: () => ({ mutateAsync: vi.fn(), isPending: false }) }));
const menuLabels = async () => within(await screen.findByRole('menu')).getAllByRole('menuitem').map((i) => (i.textContent || '').trim());
const noMenuItems = async () => { await Promise.resolve(); return screen.queryAllByRole('menuitem').map((i) => (i.textContent || '').trim()); };
const wrap = (ui: React.ReactElement) => render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);

vi.mock('@/components/common/RecordNavigation', () => ({ default: () => <div />, RecordNavigation: () => <div /> }));
vi.mock('@/components/audit/AuditTrail', () => ({ default: () => <div /> }));
vi.mock('./SupersedeDialog', () => ({ SupersedeDialog: () => null }));
vi.mock('./TermFormDialog', () => ({ TermFormDialog: () => null }));
vi.mock('../hooks/useWarrantyConfig', () => ({
  usePolicy: () => ({ data: { id: 'pol-15', version: 'v15', effective_from: '2000-01-01', effective_to: null, policy_text: null, term_count: 1, created_at: '2000-01-01T00:00:00', updated_at: null }, isLoading: false, isError: false }),
  usePolicyTerms: () => ({ data: [{ id: 't-1', policy_id: 'pol-15', kind_id: 'k-1', part_name: 'Ceramic Body', duration_months: null, is_lifetime: true, covered_defect_type_ids: null, installation_included: true, qualifications: null, exclusions: null }], isLoading: false, isError: false }),
  useKindOptions: () => ({ data: [{ id: 'k-1', name: 'Water Closet' }] }),
  useDefectOptions: () => ({ data: [] }),
}));

import PolicyDetail from './PolicyDetail';

beforeEach(() => { isAdmin = true; window.history.replaceState(null, '', '/after-sales/warranty/policies/pol-15?tab=terms'); });

describe('PolicyDetail review round', () => {
  it('the Terms tab Create button is outline, not the filled primary', () => {
    wrap(<PolicyDetail policyId="pol-15" />);
    const create = screen.getByRole('button', { name: /^Create/ });
    expect(create.className).toContain('border-input');
    expect(create.className).not.toContain('bg-primary');
  });

  it('Supersede stays the one filled button', () => {
    wrap(<PolicyDetail policyId="pol-15" />);
    expect(screen.getByRole('button', { name: 'Supersede' }).className).toContain('bg-primary');
  });
});
