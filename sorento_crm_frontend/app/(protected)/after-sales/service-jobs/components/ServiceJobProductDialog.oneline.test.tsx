/**
 * AFTER-SALES-P2 browser pass: a product name stays on one line in the Add product picker (one-line rule). jsdom cannot
 * measure overflow, so this pins what the repo's SearchableSelect needs for it: the Product select is rendered with
 * `truncateTriggerLabel` (trigger label gets `truncate` and a `title`), and not with `wrapOptions`.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

const seen: Record<string, Record<string, unknown>> = {};
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (p: Record<string, unknown>) => {
    seen[String(p['aria-label'])] = p;
    return <span />;
  },
}));
vi.mock('../services/serviceJobService', () => ({ searchCatalogueProducts: vi.fn(async () => []), getDefectOptions: vi.fn(async () => []) }));
vi.mock('../../warranty/services/warrantyConfigService', () => ({
  testKindRules: vi.fn(), getKinds: vi.fn(async () => ({ data: [], pagination: { total: 0, page: 1, limit: 100 } })),
}));
const noop = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false };
vi.mock('../hooks/useServiceJobProducts', () => ({ useServiceJobProductMutations: () => ({ add: noop, update: noop }) }));

import ServiceJobProductDialog from './ServiceJobProductDialog';

describe('Add product picker keeps names on one line', () => {
  it('the Product select truncates its label and does not wrap options', () => {
    render(<QueryClientProvider client={new QueryClient()}><ServiceJobProductDialog open onOpenChange={vi.fn()} jobId="j-1" /></QueryClientProvider>);
    expect(seen.Product.truncateTriggerLabel).toBe(true);
    expect(seen.Product.wrapOptions).toBeFalsy();
  });
});
