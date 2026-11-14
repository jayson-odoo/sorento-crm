/**
 * SPARE-PART-ORDER-REQUEST F5 (UAC R1, R2, R5, R6): the New spare part request form.
 * Header fields Currency, Delivery date (C5.1, was Needed by), Default location, Reason; a lines table with Product,
 * Location, Qty, Unit price, Total; "Submit" is the ONE filled main button and "Save as
 * draft" is secondary (owner standing rule: one filled main button per page).
 *
 * TEST-FIRST (Phase 2): the component does not exist yet, so the red is "Failed to resolve
 * import ./SparePartRequestForm". Every HTTP call goes through a mocked `apiFetch` (answers
 * empty lists), so the test holds however the coder splits hooks and services. The component
 * may be the default or the named export `SparePartRequestForm`; it renders with no props for
 * Create (Edit passes an id, R6, not asserted here).
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/project-sales/order-inquiries/spare-part-requests/new',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
  useHasAnyPermission: () => true,
  usePermissions: () => ({
    permissionSet: new Set(['procurement.spare_part_requests.create']),
    permissions: ['procurement.spare_part_requests.create'],
    isLoading: false,
    isError: false,
  }),
}));

const apiFetch = vi.fn(async (url: string) => {
  const payload = /lookup|select|options/.test(url) ? [] : { data: [], total: 0, pagination: { total: 0 } };
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
});
vi.mock('@/lib/api', () => ({ apiFetch: (...a: [string, RequestInit?]) => apiFetch(...a) }));

import * as FormModule from './SparePartRequestForm';

const SparePartRequestForm = ((FormModule as Record<string, unknown>).SparePartRequestForm ??
  (FormModule as Record<string, unknown>).default) as React.ComponentType<Record<string, unknown>>;

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SparePartRequestForm />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('F5 / UAC R1-R2: the New spare part request form', () => {
  it('renders the header fields Currency, Delivery date, Default location, Reason', async () => {
    mount();
    for (const label of ['Currency', 'Delivery date', 'Default location', 'Reason']) {
      expect((await screen.findAllByText(new RegExp(`^${label}\\b`))).length).toBeGreaterThan(0);
    }
  });

  it('renders a lines table with Product, Location, Qty, Unit price, Total', async () => {
    mount();
    for (const title of ['Product', 'Location', 'Qty', 'Unit price', 'Total']) {
      expect(
        await screen.findByRole('columnheader', { name: new RegExp(`^${title}$`) }),
      ).toBeInTheDocument();
    }
  });

  it('Submit is the one filled main button; Save as draft is secondary', async () => {
    mount();
    const submit = await screen.findByRole('button', { name: 'Submit' });
    const draft = screen.getByRole('button', { name: 'Save as draft' });
    expect(submit.className).toMatch(/\bbg-primary\b/);
    expect(draft.className).not.toMatch(/\bbg-primary\b/);
  });
});
