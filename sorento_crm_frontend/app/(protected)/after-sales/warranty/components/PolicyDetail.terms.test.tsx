/**
 * AFTER-SALES-P2 red tests (UAC C3, P1, F3): editing terms on the policy page's Terms tab.
 *
 * `./PolicyDetail` (the Terms tab) uses `./TermFormDialog` (named export, props { open, onOpenChange, policyId, term? },
 * stubbed here). Admin = `useEffectiveIsSuperadmin()` from `@/hooks/useEffectiveIsSuperadmin` (true for role admin or
 * superadmin, the same gate as the sidebar item). For an admin the Terms tab toolbar has ONE "Create" button
 * (opens the dialog in create mode for this policy); right-click on a term row opens a menu with Edit (dialog in edit
 * mode for that term) and Delete (a deferred countdown action, `useDeferredRowAction` with actionKey
 * "warranty_term.delete", called with { id, subject }; never a confirm dialog). A non-admin sees none of it.
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
  usePathname: () => '/after-sales/warranty/policies/pol-15',
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
vi.mock('@/components/common/RecordNavigation', () => ({ default: () => <div />, RecordNavigation: () => <div /> }));
vi.mock('@/components/audit/AuditTrail', () => ({ default: () => <div /> }));
vi.mock('./SupersedeDialog', () => ({ SupersedeDialog: () => null }));
vi.mock('./TermFormDialog', () => ({
  TermFormDialog: ({ open, policyId, term }: { open: boolean; policyId: string; term?: { id: string; part_name: string } | null }) =>
    open ? <div role="dialog">Term form {term ? `edit ${term.part_name}` : `create for ${policyId}`}</div> : null,
}));

const usePolicyTerms = vi.fn();
vi.mock('../hooks/useWarrantyConfig', () => ({
  usePolicy: () => ({ data: { id: 'pol-15', version: 'v15', effective_from: '2000-01-01', effective_to: null, policy_text: null, term_count: 2, created_at: '2000-01-01T00:00:00', updated_at: null }, isLoading: false, isError: false }),
  usePolicyTerms: (...a: unknown[]) => usePolicyTerms(...a),
  useKindOptions: () => ({ data: [{ id: 'k-1', name: 'Water Closet' }] }),
  useDefectOptions: () => ({ data: [{ id: 'd-1', label: 'Crack line' }] }),
}));

import PolicyDetail from './PolicyDetail';

const term = (over: Record<string, unknown>) => ({ id: 't-1', policy_id: 'pol-15', kind_id: 'k-1', part_name: 'Ceramic Body', duration_months: null, is_lifetime: true, covered_defect_type_ids: ['d-1'], installation_included: true, qualifications: null, exclusions: null, ...over });
const TERMS = [term({}), term({ id: 't-2', part_name: 'Flushing Fittings', is_lifetime: false, duration_months: 60, covered_defect_type_ids: null })];
const renderPage = () => render(<QueryClientProvider client={new QueryClient()}><PolicyDetail policyId="pol-15" /></QueryClientProvider>);
const menuLabels = async () => within(await screen.findByRole('menu')).getAllByRole('menuitem').map((i) => (i.textContent || '').trim());

beforeEach(() => {
  vi.clearAllMocks();
  isAdmin = true;
  Object.keys(runs).forEach((k) => delete runs[k]);
  window.history.replaceState(null, '', '/after-sales/warranty/policies/pol-15');
  usePolicyTerms.mockReturnValue({ data: TERMS, isLoading: false, isError: false });
});

describe('PolicyDetail Terms tab editing', () => {
  it('an admin sees one Create button on the Terms tab and it opens the create dialog for this policy', () => {
    renderPage();
    const create = screen.getAllByRole('button', { name: /^Create/ });
    expect(create).toHaveLength(1);
    fireEvent.click(create[0]);
    expect(screen.getByRole('dialog')).toHaveTextContent('Term form create for pol-15');
  });

  it('the Create button stays when the policy has no terms yet, outside the empty state', () => {
    usePolicyTerms.mockReturnValue({ data: [], isLoading: false, isError: false });
    renderPage();
    expect(screen.getAllByRole('button', { name: /^Create/ })).toHaveLength(1);
    const heading = screen.getByRole('heading', { name: /no terms/i });
    expect(within(heading.parentElement as HTMLElement).queryByRole('button')).toBeNull();
  });

  it('right-click on a term row offers Edit and Delete, and Edit opens the dialog on that term', async () => {
    renderPage();
    fireEvent.contextMenu(screen.getByText('Flushing Fittings'));
    expect(await menuLabels()).toEqual(['Edit', 'Delete']);
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Edit' }));
    expect(screen.getByRole('dialog')).toHaveTextContent('Term form edit Flushing Fittings');
  });

  it('Delete is a deferred countdown action on that term and never a confirm', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    renderPage();
    fireEvent.contextMenu(screen.getByText('Flushing Fittings'));
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Delete' }));
    const key = Object.keys(runs).find((k) => /term/.test(k) && /delete/.test(k));
    expect(key).toBe('warranty_term.delete');
    expect(runs[key!]).toHaveBeenCalledWith(expect.objectContaining({ id: 't-2' }));
    expect(confirm).not.toHaveBeenCalled();
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });

  it('a non-admin sees no Create and no row menu', async () => {
    isAdmin = false;
    renderPage();
    expect(screen.queryByRole('button', { name: /^Create/ })).toBeNull();
    fireEvent.contextMenu(screen.getByText('Flushing Fittings'));
    await Promise.resolve();
    expect(screen.queryByRole('menu')).toBeNull();
    expect(screen.queryByRole('menuitem', { name: 'Edit' })).toBeNull();
    expect(screen.queryByRole('menuitem', { name: 'Delete' })).toBeNull();
  });
});
