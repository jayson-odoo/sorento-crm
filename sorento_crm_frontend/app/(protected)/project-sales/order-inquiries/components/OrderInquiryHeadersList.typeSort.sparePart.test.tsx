/**
 * SPARE-PART-ORDER-REQUEST fix round 2, R6 (review S6; owner rule "every column header sorts,
 * on the server"): the Type column is sortable, and sorting it asks the server for
 * `sort=inquiry_type` (the backend half is `tests/test_spare_part_request_fix2.py::test_R6_*`).
 * Harness copied from `OrderInquiryHeadersList.sparePart.test.tsx`; the hook mock records the
 * params the list asks with.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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

const replace = vi.fn();
const push = vi.fn();
vi.mock('next/navigation', () => ({
  usePathname: () => '/project-sales/order-inquiries',
  useRouter: () => ({ push, replace }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/services/userSelectService', () => ({ getUserLookup: vi.fn(async () => []) }));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => false }));

const asked: Array<Record<string, unknown>> = [];
vi.mock('../../_shared/hooks/useOrderInquiry', () => ({
  useOrderInquiryHeaders: (params: Record<string, unknown>) => {
    asked.push(params);
    return {
      data: {
        data: [
          { id: 'h-1', inquiry_no: 'OI-2611-0001', inquiry_type: 'sales_order', so_number: 'SO1', status: 'open', raised_at: '2026-11-01T00:00:00' },
          { id: 'h-2', inquiry_no: 'OI-2611-0007', inquiry_type: 'spare_part_request', so_number: null, status: 'open', raised_at: '2026-11-12T00:00:00' },
        ],
        total: 2,
      },
      isLoading: false,
      isPlaceholderData: false,
      isFetching: false,
      refetch: vi.fn(),
      error: null,
    };
  },
  useOrderInquiryWorklistSummary: () => ({ data: { agents: [], projects: [] } }),
  useReserveStatusSummary: () => ({ data: undefined }),
  useParkedPreview: () => ({ data: undefined, isLoading: false }),
  useSendParked: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useHandoverResendPreview: () => ({ data: undefined, isLoading: false, error: null }),
  useSendHandoverResend: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

import { OrderInquiryHeadersList } from './OrderInquiryHeadersList';

function renderList() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <OrderInquiryHeadersList />
    </QueryClientProvider>,
  );
}

function typeHeader(): HTMLElement {
  const cell = screen
    .getAllByRole('columnheader')
    .find((c) => (c.textContent ?? '').trim() === 'Type');
  expect(cell, 'a Type column').toBeDefined();
  return cell as HTMLElement;
}

/** The header's own controls, without the column drag handle every header carries. */
function sortControls(cell: HTMLElement): HTMLElement[] {
  return within(cell)
    .queryAllByRole('button')
    .filter((b) => b.getAttribute('aria-label') !== 'Drag column to reorder');
}

describe('R6 / S6: the Type column sorts on the server', () => {
  it('the Type header carries a sort control, like S/O no', () => {
    renderList();
    const soNo = screen
      .getAllByRole('columnheader')
      .find((c) => (c.textContent ?? '').trim() === 'S/O no') as HTMLElement;
    expect(sortControls(soNo).length, 'control: S/O no sorts').toBeGreaterThan(0);
    expect(sortControls(typeHeader()).length).toBeGreaterThan(0);
  });

  it('clicking Type asks the server for sort=inquiry_type', async () => {
    renderList();
    const controls = sortControls(typeHeader());
    expect(controls.length).toBeGreaterThan(0);
    fireEvent.click(controls[0]);
    await waitFor(() => {
      const viaHook = asked.some((p) => p.sort === 'inquiry_type');
      const viaUrl = [...replace.mock.calls, ...push.mock.calls].some((c) =>
        String(c[0]).includes('sort=inquiry_type'),
      );
      expect(viaHook || viaUrl).toBe(true);
    });
  });
});
