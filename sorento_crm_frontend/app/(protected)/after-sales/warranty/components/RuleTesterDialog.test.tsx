/**
 * AFTER-SALES-P2 red tests (UAC F3, K): the "Test a product" dialog on the Rules tab. Ported from #163
 * `RuleTesterCard.test.tsx`, now a dialog.
 *
 * Module the coder builds: `./RuleTesterDialog` named export `RuleTesterDialog`, props { open, onOpenChange }.
 * One field: Product (async SearchableSelect, aria-label "Product", fetchOptions over `searchCatalogueProducts` from
 * `../../service-jobs/services/serviceJobService`). Picking a product runs `useTestKindRules().mutateAsync(productId)` from
 * `../hooks/useWarrantyConfig` -> { resolved_kind: {id, code, name} | null, deciding_rule: {id, match_type, match_value} | null }.
 * It shows the winning kind name, the rule's match type word and value; with no match it shows exactly
 * "No warranty rule for this product yet". Only a Close button (read-only dialog).
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

type Opt = { value: string; label: string };
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (p: { value: string; onChange: (v: string) => void; onOptionChange?: (o: Opt | null) => void; options?: Opt[]; fetchOptions?: (q: string, i: number) => Promise<Opt[]>; 'aria-label'?: string }) => {
    const [fetched, setFetched] = React.useState<Opt[]>([]);
    React.useEffect(() => { p.fetchOptions?.('', 0).then(setFetched); }, []); // eslint-disable-line
    const all = [...(p.options ?? []), ...fetched];
    return (
      <select aria-label={p['aria-label']} value={p.value} onChange={(e) => { p.onChange(e.target.value); p.onOptionChange?.(all.find((o) => o.value === e.target.value) ?? null); }}>
        <option value="">-</option>
        {all.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    );
  },
}));
vi.mock('../../service-jobs/services/serviceJobService', () => ({
  searchCatalogueProducts: vi.fn(async () => [
    { id: 'p-1', product_code: 'DEMO-WC-02', product_name: 'Demo one piece water closet' },
    { id: 'p-2', product_code: 'ZZZ-1', product_name: 'Unmatched thing' },
  ]),
}));
const test = vi.fn();
vi.mock('../hooks/useWarrantyConfig', () => ({ useTestKindRules: () => ({ mutateAsync: (...a: unknown[]) => test(...a), isPending: false }) }));

import { RuleTesterDialog } from './RuleTesterDialog';

const setup = () => render(<QueryClientProvider client={new QueryClient()}><RuleTesterDialog open onOpenChange={vi.fn()} /></QueryClientProvider>);

beforeEach(() => vi.clearAllMocks());

describe('RuleTesterDialog', () => {
  it('shows the winning kind and the rule that decided it', async () => {
    test.mockResolvedValue({ resolved_kind: { id: 'k-1', code: 'WC', name: 'Water Closet' }, deciding_rule: { id: 'r-1', match_type: 'series', match_value: 'Demo Series A' } });
    setup();
    await screen.findByRole('option', { name: /DEMO-WC-02/ });
    fireEvent.change(screen.getByLabelText('Product'), { target: { value: 'p-1' } });
    await waitFor(() => expect(test).toHaveBeenCalledWith('p-1'));
    expect(await screen.findByText('Water Closet')).toBeInTheDocument();
    expect(screen.getByText('Series')).toBeInTheDocument();
    expect(screen.getByText('Demo Series A')).toBeInTheDocument();
  });

  it('no match says exactly "No warranty rule for this product yet"', async () => {
    test.mockResolvedValue({ resolved_kind: null, deciding_rule: null });
    setup();
    await screen.findByRole('option', { name: /ZZZ-1/ });
    fireEvent.change(screen.getByLabelText('Product'), { target: { value: 'p-2' } });
    expect(await screen.findByText('No warranty rule for this product yet')).toBeInTheDocument();
  });

  it('shows nothing before a product is picked and never renders a UUID', async () => {
    setup();
    await screen.findByRole('option', { name: /DEMO-WC-02/ });
    expect(test).not.toHaveBeenCalled();
    expect(screen.queryByText('No warranty rule for this product yet')).toBeNull();
    expect(screen.getByRole('dialog').textContent).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-/i);
  });
});
