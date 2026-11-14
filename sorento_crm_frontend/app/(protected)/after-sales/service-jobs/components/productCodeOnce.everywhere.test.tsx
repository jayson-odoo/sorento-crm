/**
 * AFTER-SALES-P2 crew pass on a1b04227 (owner standing rules):
 * 1. A product never shows a name that is just its code: outside the picker too, the code shows once through the
 *    shared rule (`lib/product-display.ts`): the Warranty card's Product cell reads `codeWithName`, the Products grid's
 *    Description is blank ("-") when the name equals the code, and the Remove countdown's subject reads `codeWithName`.
 * 2. No "how this works" text in the P2 dialogs: none of them carries a DialogDescription (not even sr-only).
 */
import React from 'react';
import fs from 'node:fs';
import path from 'node:path';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, fireEvent, within } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };

const run = vi.fn();
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: () => ({ run, targetId: null, isPending: false, countdown: null }),
  useRowPending: () => () => false,
}));
const line = (over: Record<string, unknown>) => ({
  id: 'l-1', product_id: 'p-1', product_code: 'CB110', product_name: 'CB110', kind_id: null, kind_name: null,
  purchase_date: '2020-03-15', defect_type_id: null, defect_label: null, sort_order: 0, ...over,
});
let lines: unknown[] = [];
vi.mock('../hooks/useServiceJobProducts', () => ({
  useServiceJobProducts: () => ({ data: lines, isLoading: false, isError: false, refetch: vi.fn() }),
  useServiceJobProductMutations: () => ({ add: { mutateAsync: vi.fn(), isPending: false }, update: { mutateAsync: vi.fn(), isPending: false } }),
}));
vi.mock('../services/serviceJobService', () => ({ searchCatalogueProducts: vi.fn(async () => []), getDefectOptions: vi.fn(async () => []) }));
vi.mock('../../warranty/services/warrantyConfigService', () => ({
  testKindRules: vi.fn(), getKinds: vi.fn(async () => ({ data: [], pagination: { total: 0, page: 1, limit: 100 } })),
}));

import ServiceJobWarrantyCard from './ServiceJobWarrantyCard';
import ServiceJobProductsCard from './ServiceJobProductsCard';

const verdict = { part_name: 'Body', verdict: 'unknown', expiry: null, reason: 'No warranty rule for this product yet', is_lifetime: false, installation_included: false, policy_version: null };
const count = (text: string, code: string) => text.split(code).length - 1;

beforeEach(() => { run.mockClear(); lines = []; });

describe('the product code shows once outside the picker', () => {
  it('Warranty card Product cell', () => {
    render(
      <ServiceJobWarrantyCard
        warranty={[
          { id: 'a', product_code: 'CB110', product_name: 'CB110', kind_name: null, purchase_date: null, defect_label: null, verdicts: [verdict] },
          { id: 'b', product_code: 'SRTWC6020-SH-UF', product_name: 'Wall hung water closet', kind_name: null, purchase_date: null, defect_label: null, verdicts: [verdict] },
        ]}
      />,
    );
    const text = document.body.textContent ?? '';
    expect(count(text, 'CB110')).toBe(1);
    expect(screen.getByText('SRTWC6020-SH-UF - Wall hung water closet')).toBeInTheDocument();
  });

  it('Products grid: Description is blank when the name equals the code; Remove names the product once', async () => {
    lines = [line({})];
    render(<QueryClientProvider client={new QueryClient()}><ServiceJobProductsCard jobId="j-1" canEdit /></QueryClientProvider>);
    const row = screen.getAllByRole('row').find((r) => (r.textContent ?? '').includes('CB110')) as HTMLElement;
    expect(count(row.textContent ?? '', 'CB110')).toBe(1);
    fireEvent.contextMenu(row);
    fireEvent.click(within(await screen.findByRole('menu')).getByRole('menuitem', { name: 'Remove' }));
    expect(run).toHaveBeenCalledWith(expect.objectContaining({ id: 'l-1', subject: 'CB110' }));
  });
});

describe('P2 dialogs carry no explanatory description', () => {
  const ROOT = path.join(process.cwd(), 'app', '(protected)', 'after-sales');
  const files = [
    'warranty/components/RuleTesterDialog.tsx',
    'warranty/components/TermFormDialog.tsx',
    'warranty/components/KindFormDialog.tsx',
    'warranty/components/RuleFormDialog.tsx',
    'warranty/components/PolicyFormDialog.tsx',
    'warranty/components/SupersedeDialog.tsx',
    'service-jobs/components/ServiceJobProductDialog.tsx',
  ];
  it.each(files)('%s has no DialogDescription', (file) => {
    const src = fs.readFileSync(path.join(ROOT, file), 'utf8');
    expect(src).not.toMatch(/<DialogDescription/);
    expect(src).not.toMatch(/See which kind the rules give a product|Warranty term\./);
  });
});
