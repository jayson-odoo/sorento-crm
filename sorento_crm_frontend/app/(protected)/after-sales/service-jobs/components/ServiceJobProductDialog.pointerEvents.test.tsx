/**
 * AFTER-SALES-P2 browser re-run: closing the Add product dialog opened from the Products card (nothing picked) must give
 * the page back: `document.body.style.pointerEvents` must not stay "none" after Escape or after the close button. Real
 * dialog and real SearchableSelect. jsdom may not reproduce the browser's stuck state; the assertion is the contract.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: () => ({ run: vi.fn(), targetId: null, isPending: false, countdown: null }),
  useRowPending: () => () => false,
}));
const noop = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false };
vi.mock('../hooks/useServiceJobProducts', () => ({
  useServiceJobProducts: () => ({ data: [], isLoading: false, isError: false, refetch: vi.fn() }),
  useServiceJobProductMutations: () => ({ add: noop, update: noop }),
}));
vi.mock('../services/serviceJobService', () => ({ searchCatalogueProducts: vi.fn(async () => []), getDefectOptions: vi.fn(async () => []) }));
vi.mock('../../warranty/services/warrantyConfigService', () => ({
  testKindRules: vi.fn(), getKinds: vi.fn(async () => ({ data: [], pagination: { total: 0, page: 1, limit: 100 } })),
}));

import ServiceJobProductsCard from './ServiceJobProductsCard';

const open = async () => {
  render(<QueryClientProvider client={new QueryClient()}><ServiceJobProductsCard jobId="j-1" canEdit /></QueryClientProvider>);
  await userEvent.click(screen.getByRole('button', { name: 'Add product' }));
  await screen.findByRole('dialog');
};
const settled = () => waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());

beforeEach(() => { document.body.style.pointerEvents = ''; });

describe('Add product dialog gives the page back when closed', () => {
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
