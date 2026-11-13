/**
 * AFTER-SALES-P2 browser re-run: closing the Rules tab "Test a product" dialog (nothing picked) must give the page back.
 * `document.body.style.pointerEvents` must not stay "none" after Escape or after the close button. Opened the way the
 * tab opens it (its "Test a product" button), with the real dialog and the real SearchableSelect. jsdom may not
 * reproduce the browser's stuck state; the assertion is the contract either way.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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
vi.mock('@/hooks/useEffectiveIsSuperadmin', () => ({ useEffectiveIsSuperadmin: () => true }));
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: () => ({ run: vi.fn(), targetId: null, isPending: false, countdown: null }),
  useRowPending: () => () => false,
}));
const { mut } = vi.hoisted(() => ({ mut: () => ({ mutateAsync: vi.fn(), isPending: false }) }));
vi.mock('../hooks/useWarrantyConfig', () => ({
  useRules: () => ({ data: { data: [], pagination: { total: 0, page: 1, limit: 50 } }, isLoading: false, isError: false, isFetching: false, refetch: vi.fn() }),
  useKindOptions: () => ({ data: [] }),
  useCreateRule: mut, useUpdateRule: mut,
  useTestKindRules: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock('./RuleFormDialog', () => ({ RuleFormDialog: () => null }));
vi.mock('../../service-jobs/services/serviceJobService', () => ({ searchCatalogueProducts: vi.fn(async () => []) }));

import { RulesTab } from './RulesTab';

const open = async () => {
  render(<QueryClientProvider client={new QueryClient()}><RulesTab /></QueryClientProvider>);
  fireEvent.click(screen.getByRole('button', { name: /Test a product/ }));
  await screen.findByRole('dialog');
};
const settled = () => waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());

beforeEach(() => { document.body.style.pointerEvents = ''; });

describe('Test a product dialog gives the page back when closed', () => {
  it('Escape', async () => {
    await open();
    await userEvent.keyboard('{Escape}');
    await settled();
    expect(document.body.style.pointerEvents).not.toBe('none');
  });

  it('the close button', async () => {
    await open();
    await userEvent.click(document.querySelector('[data-slot="dialog-close"]') as HTMLElement);
    await settled();
    expect(document.body.style.pointerEvents).not.toBe('none');
  });
});
