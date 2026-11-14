/**
 * AFTER-SALES-P2 red tests (UAC C supersede, F3): the Supersede dialog states BOTH versions' date ranges
 * before anything is saved. Ported from #163 `PolicyFormDialog.supersedeMinDate.test.tsx`.
 *
 * Module the coder builds: `./SupersedeDialog` named export `SupersedeDialog`, props
 *   { open, onOpenChange, policy: Policy }   (the incumbent)
 * Fields: New version (aria-label "New version"), Starts on (DatePicker, aria-label "Starts on").
 * One line under them, exactly: `<old> closes <dd/mm/yyyy>; <new> runs from <dd/mm/yyyy>` (the day before the
 * new start). Main button "Supersede", disabled unless the start is strictly AFTER the incumbent's own start.
 * Calls `useSupersedePolicy().mutateAsync({ id, values: { version, effective_from } })` from `../hooks/useWarrantyConfig`.
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

const supersede = { mutateAsync: vi.fn().mockResolvedValue({}), isPending: false };
vi.mock('../hooks/useWarrantyConfig', () => ({ useSupersedePolicy: () => supersede }));

import { SupersedeDialog } from './SupersedeDialog';

const POLICY = { id: 'pol-15', version: 'v15', effective_from: '2000-01-01', effective_to: null, policy_text: null, term_count: 41 };
const onOpenChange = vi.fn();

function setup(policy = POLICY) {
  render(<QueryClientProvider client={new QueryClient()}><SupersedeDialog open onOpenChange={onOpenChange} policy={policy as never} /></QueryClientProvider>);
}
function fill(version: string, date: string) {
  fireEvent.change(screen.getByLabelText('New version'), { target: { value: version } });
  const starts = screen.getByLabelText('Starts on');
  fireEvent.change(starts, { target: { value: date } });
  fireEvent.blur(starts);
}

beforeEach(() => vi.clearAllMocks());

describe('SupersedeDialog', () => {
  it('shows both versions date ranges before saving', () => {
    setup();
    fill('v16', '01/01/2027');
    expect(screen.getByText('v15 closes 31/12/2026; v16 runs from 01/01/2027')).toBeInTheDocument();
  });

  it('rolls the close date across a month and year boundary', () => {
    setup();
    fill('v16', '01/03/2027');
    expect(screen.getByText('v15 closes 28/02/2027; v16 runs from 01/03/2027')).toBeInTheDocument();
  });

  it('a start on or before the incumbent start is refused: no impossible close date, button disabled', () => {
    setup({ ...POLICY, effective_from: '2026-01-01' });
    fill('v16', '01/01/2026');
    expect(screen.getByRole('dialog').textContent).not.toMatch(/31\/12\/2025/);
    expect(screen.getByRole('button', { name: 'Supersede' })).toBeDisabled();
  });

  it('saves with the new version and a YYYY-MM-DD start, then closes', async () => {
    setup();
    fill('v16', '01/01/2027');
    fireEvent.click(screen.getByRole('button', { name: 'Supersede' }));
    await waitFor(() =>
      expect(supersede.mutateAsync).toHaveBeenCalledWith({ id: 'pol-15', values: { version: 'v16', effective_from: '2027-01-01' } }),
    );
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it('is a plain dialog: no confirm() and no alert dialog', () => {
    const confirm = vi.spyOn(window, 'confirm');
    setup();
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(confirm).not.toHaveBeenCalled();
  });
});
