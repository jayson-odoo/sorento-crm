/**
 * AFTER-SALES-P2 red tests (UAC C, F3): create and edit a warranty policy (one dialog, same fields).
 *
 * Module the coder builds: `./PolicyFormDialog` named export `PolicyFormDialog`, props
 *   { open, onOpenChange, policy?: Policy | null }   (policy set = Edit)
 * Fields: Version, In force from (DatePicker, aria-label "In force from"), In force to (DatePicker, optional,
 * aria-label "In force to"), Policy text. Main button "Create" (new) or "Save" (edit). Mutations from
 * `../hooks/useWarrantyConfig`: useCreatePolicy().mutateAsync({ version, effective_from, effective_to, policy_text })
 * and useUpdatePolicy().mutateAsync({ id, values }). Dates are sent as YYYY-MM-DD.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

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

const create = { mutateAsync: vi.fn().mockResolvedValue({}), isPending: false };
const update = { mutateAsync: vi.fn().mockResolvedValue({}), isPending: false };
vi.mock('../hooks/useWarrantyConfig', () => ({ useCreatePolicy: () => create, useUpdatePolicy: () => update }));

import { PolicyFormDialog } from './PolicyFormDialog';

const onOpenChange = vi.fn();
const setup = (policy: unknown = null) =>
  render(<QueryClientProvider client={new QueryClient()}><PolicyFormDialog open onOpenChange={onOpenChange} policy={policy as never} /></QueryClientProvider>);

beforeEach(() => vi.clearAllMocks());

describe('PolicyFormDialog', () => {
  it('create: Version and In force from are required, so nothing is sent while empty', async () => {
    setup();
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));
    await waitFor(() => expect(screen.getAllByText(/required/i).length).toBeGreaterThan(0));
    expect(create.mutateAsync).not.toHaveBeenCalled();
  });

  it('create: sends the dates as YYYY-MM-DD and an empty end as null', async () => {
    setup();
    fireEvent.change(screen.getByLabelText(/^Version/), { target: { value: 'v16' } });
    const from = screen.getByLabelText('In force from');
    fireEvent.change(from, { target: { value: '01/01/2027' } });
    fireEvent.blur(from);
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));
    await waitFor(() =>
      expect(create.mutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({ version: 'v16', effective_from: '2027-01-01', effective_to: null }),
      ),
    );
  });

  it('edit: pre-fills the policy with dd/mm/yyyy dates and saves with update', async () => {
    setup({ id: 'pol-15', version: 'v15', effective_from: '2000-01-01', effective_to: '2026-12-31', policy_text: 'Terms apply', term_count: 3 });
    expect(screen.getByLabelText(/^Version/)).toHaveValue('v15');
    expect(screen.getByDisplayValue('01/01/2000')).toBeInTheDocument();
    expect(screen.getByDisplayValue('31/12/2026')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/^Version/), { target: { value: 'v15b' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(update.mutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({ id: 'pol-15', values: expect.objectContaining({ version: 'v15b', effective_from: '2000-01-01', effective_to: '2026-12-31' }) }),
      ),
    );
  });
});
