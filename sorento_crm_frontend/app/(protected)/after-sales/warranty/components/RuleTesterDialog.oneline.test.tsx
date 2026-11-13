/**
 * AFTER-SALES-P2 browser pass: a product name stays on one line in the rule tester picker (one-line rule). jsdom cannot
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
vi.mock('../../service-jobs/services/serviceJobService', () => ({ searchCatalogueProducts: vi.fn(async () => []) }));
vi.mock('../hooks/useWarrantyConfig', () => ({ useTestKindRules: () => ({ mutateAsync: vi.fn(), isPending: false }) }));

import { RuleTesterDialog } from './RuleTesterDialog';

describe('Rule tester picker keeps names on one line', () => {
  it('the Product select truncates its label and does not wrap options', () => {
    render(<QueryClientProvider client={new QueryClient()}><RuleTesterDialog open onOpenChange={vi.fn()} /></QueryClientProvider>);
    expect(seen.Product.truncateTriggerLabel).toBe(true);
    expect(seen.Product.wrapOptions).toBeFalsy();
  });
});
