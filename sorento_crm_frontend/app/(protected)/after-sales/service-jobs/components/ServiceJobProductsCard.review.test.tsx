/**
 * AFTER-SALES-P2 review round (item 10): one filled main button per page. The job page's filled button is its header
 * action, so the Products card's "Add product" is an OUTLINE button (the repo's Button `variant="outline"`:
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

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

const lines = vi.fn();
vi.mock('../hooks/useServiceJobProducts', () => ({
  useServiceJobProducts: () => lines(),
  useServiceJobProductMutations: () => ({
    add: { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false },
    update: { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false },
  }),
}));

const run = vi.fn();
const deferredInputs: Record<string, unknown>[] = [];
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: (input: Record<string, unknown>) => {
    deferredInputs.push(input);
    return { run, targetId: null, isPending: false, countdown: null };
  },
  useRowPending: () => () => false,
}));

vi.mock('./ServiceJobProductDialog', () => ({
  default: ({ open, line }: { open: boolean; line?: { id: string } | null }) =>
    open ? <div role="dialog">Product dialog {line ? `edit ${line.id}` : 'add'}</div> : null,
}));

import ServiceJobProductsCard from './ServiceJobProductsCard';


const LINE = { id: 'line-1', product_id: 'p-1', product_code: 'DEMO-WC-02', product_name: 'Demo one piece water closet', kind_id: null, kind_name: null, purchase_date: null, defect_type_id: null, defect_label: null, sort_order: 0 };

describe('ServiceJobProductsCard review round', () => {
  it('Add product is an outline button, not the filled primary', () => {
    lines.mockReturnValue({ data: [LINE], isLoading: false, isError: false, refetch: vi.fn() });
    render(<QueryClientProvider client={new QueryClient()}><ServiceJobProductsCard jobId="j-1" canEdit /></QueryClientProvider>);
    const add = screen.getByRole('button', { name: 'Add product' });
    expect(add.className).toContain('border-input');
    expect(add.className).not.toContain('bg-primary');
  });
});
