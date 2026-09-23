/**
 * AC-14/AC-15 (PLAN-brand-flows-to-purchasing.md) on the brand RECORD page - the one
 * users actually edit a brand from (fix round, 23 Sep 2026: `BrandForm` and
 * `BrandFormDialog` both carry the switch, but neither is mounted here - this page has
 * its own inline view/edit layout with its own draft state, so a defect in ITS copy of
 * the switch/save logic would ship unnoticed with only the other two covered).
 *
 * Pattern borrowed from `../../../inventory-management/warehouses/[id]/page.test.tsx`:
 * the page resolves `params` with `use()`, which suspends on the first render, and
 * `Container` pulls `SettingsProvider` context this unit test does not mount.
 */
import React, { Suspense } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import { QueryClientProvider, QueryClient } from '@tanstack/react-query';

import type { Brand } from '../../products/types/product.types';

const BRAND_ID = '11111111-1111-4111-8111-111111111111';

const h = vi.hoisted(() => ({
  updateMutate: vi.fn(),
  brand: undefined as Brand | undefined,
}));

function brand(over: Partial<Brand> = {}): Brand {
  return {
    id: BRAND_ID,
    brand_code: 'TPE',
    brand_name: 'TP Enterprise',
    description: null,
    is_active: true,
    access_levels: [],
    flows_to_purchasing: true,
    created_at: new Date('2026-01-05T02:00:00Z'),
    updated_at: new Date('2026-02-09T04:30:00Z'),
    product_count: 4,
    ...over,
  };
}

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), back: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
  usePathname: () => `/master-data-management/brands/${BRAND_ID}`,
}));

// Container pulls SettingsProvider context this unit test does not need.
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('../hooks/useBrands', () => ({
  useBrand: () => ({ data: h.brand, isLoading: false }),
  useUpdateBrand: () => ({ mutateAsync: h.updateMutate, isPending: false }),
}));

vi.mock('@/app/(protected)/user-management/contact-access-types/hooks/useContactAccessTypes', () => ({
  useContactAccessTypes: () => ({ data: [] }),
}));

// `useDeferredAction` (delete) watches from mount, which reads this on every render.
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

import BrandDetailPage from './page';

async function renderDetail() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  await act(async () => {
    render(
      <QueryClientProvider client={client}>
        <Suspense fallback={<div>Loading route</div>}>
          <BrandDetailPage params={Promise.resolve({ id: BRAND_ID })} />
        </Suspense>
      </QueryClientProvider>,
    );
  });
}

async function startEdit() {
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
  });
}

beforeEach(() => {
  h.updateMutate.mockReset().mockResolvedValue(undefined);
  h.brand = brand();
});

describe('Brand detail - Flows to purchasing (AC-14)', () => {
  it('view mode shows the stored value', async () => {
    h.brand = brand({ flows_to_purchasing: false });
    await renderDetail();

    const page = (document.body.textContent ?? '').replace(/\s+/g, ' ');
    expect(page).toContain('Flows to purchasing');
    expect(page).toContain('No');
  });

  it('view mode shows Yes for a brand that flows to purchasing', async () => {
    h.brand = brand({ flows_to_purchasing: true });
    await renderDetail();

    const page = (document.body.textContent ?? '').replace(/\s+/g, ' ');
    expect(page).toContain('Flows to purchasing');
    expect(page).toContain('Yes');
  });

  it('edit mode: the switch reflects a stored false rather than defaulting back on', async () => {
    h.brand = brand({ flows_to_purchasing: false });
    await renderDetail();
    await startEdit();

    const toggle = screen.getByLabelText('Flows to purchasing');
    expect(toggle).toHaveAttribute('aria-checked', 'false');
  });

  it('edit mode: the switch reflects a stored true', async () => {
    h.brand = brand({ flows_to_purchasing: true });
    await renderDetail();
    await startEdit();

    const toggle = screen.getByLabelText('Flows to purchasing');
    expect(toggle).toHaveAttribute('aria-checked', 'true');
  });

  it('AC-15: an untouched save on a blocked brand keeps sending false', async () => {
    h.brand = brand({ flows_to_purchasing: false });
    await renderDetail();
    await startEdit();

    fireEvent.click(screen.getByRole('button', { name: /save brand/i }));

    await waitFor(() => expect(h.updateMutate).toHaveBeenCalled());
    const [{ data: payload }] = h.updateMutate.mock.calls[0];
    expect(payload.flows_to_purchasing).toBe(false);
  });

  it('AC-15: toggling on a default brand sends false', async () => {
    h.brand = brand({ flows_to_purchasing: true });
    await renderDetail();
    await startEdit();

    fireEvent.click(screen.getByLabelText('Flows to purchasing'));
    fireEvent.click(screen.getByRole('button', { name: /save brand/i }));

    await waitFor(() => expect(h.updateMutate).toHaveBeenCalled());
    const [{ data: payload }] = h.updateMutate.mock.calls[0];
    expect(payload.flows_to_purchasing).toBe(false);
  });
});
