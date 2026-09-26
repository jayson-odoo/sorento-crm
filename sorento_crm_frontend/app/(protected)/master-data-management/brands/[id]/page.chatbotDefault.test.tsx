/**
 * W5 (owner hand test round 2 on PR #833): the brand the chatbot answers first when a
 * customer names no brand, edited on the brand RECORD page (Master Data > Brands > a
 * brand > Edit), the page users actually edit a brand from.
 *
 * Pattern borrowed from `../../../inventory-management/warehouses/[id]/page.test.tsx`:
 * the page resolves `params` with `use()`, which suspends on the first render, and
 * `Container` pulls `SettingsProvider` context this unit test does not mount.
 */
import React, { Suspense } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  render,
  screen,
  fireEvent,
  act,
  waitFor,
} from '@testing-library/react';
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
    is_chatbot_default: false,
    created_at: new Date('2026-01-05T02:00:00Z'),
    updated_at: new Date('2026-02-09T04:30:00Z'),
    product_count: 4,
    ...over,
  };
}

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
    back: vi.fn(),
    replace: vi.fn(),
    refresh: vi.fn(),
  }),
  useSearchParams: () => new URLSearchParams(''),
  usePathname: () => `/master-data-management/brands/${BRAND_ID}`,
}));

// Container pulls SettingsProvider context this unit test does not need.
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
}));

vi.mock('../hooks/useBrands', () => ({
  useBrand: () => ({ data: h.brand, isLoading: false }),
  useUpdateBrand: () => ({ mutateAsync: h.updateMutate, isPending: false }),
}));

vi.mock(
  '@/app/(protected)/user-management/contact-access-types/hooks/useContactAccessTypes',
  () => ({
    useContactAccessTypes: () => ({ data: [] }),
  }),
);

// `useDeferredAction` (delete) watches from mount, which reads this on every render.
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi
    .fn()
    .mockResolvedValue({ pending: null, last_outcome: null }),
}));

import BrandDetailPage from './page';

async function renderDetail() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
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

describe('Brand detail - Chatbot default brand (W5)', () => {
  it('view mode says Yes for the default brand', async () => {
    h.brand = brand({ is_chatbot_default: true });
    await renderDetail();

    const page = (document.body.textContent ?? '').replace(/\s+/g, ' ');
    expect(page).toMatch(/Chatbot default brand\s*Yes/);
  });

  it('view mode says No for any other brand', async () => {
    h.brand = brand({ is_chatbot_default: false });
    await renderDetail();

    const page = (document.body.textContent ?? '').replace(/\s+/g, ' ');
    expect(page).toMatch(/Chatbot default brand\s*No/);
  });

  it('edit mode: the switch reflects the stored value', async () => {
    h.brand = brand({ is_chatbot_default: true });
    await renderDetail();
    await startEdit();

    expect(screen.getByLabelText('Chatbot default brand')).toHaveAttribute(
      'aria-checked',
      'true',
    );
  });

  it('toggling it on sends is_chatbot_default: true', async () => {
    h.brand = brand({ is_chatbot_default: false });
    await renderDetail();
    await startEdit();

    fireEvent.click(screen.getByLabelText('Chatbot default brand'));
    fireEvent.click(screen.getByRole('button', { name: /save brand/i }));

    await waitFor(() => expect(h.updateMutate).toHaveBeenCalled());
    const [{ data: payload }] = h.updateMutate.mock.calls[0];
    expect(payload.is_chatbot_default).toBe(true);
  });

  it('an untouched save keeps the stored value', async () => {
    h.brand = brand({ is_chatbot_default: true });
    await renderDetail();
    await startEdit();

    fireEvent.click(screen.getByRole('button', { name: /save brand/i }));

    await waitFor(() => expect(h.updateMutate).toHaveBeenCalled());
    const [{ data: payload }] = h.updateMutate.mock.calls[0];
    expect(payload.is_chatbot_default).toBe(true);
  });
});
