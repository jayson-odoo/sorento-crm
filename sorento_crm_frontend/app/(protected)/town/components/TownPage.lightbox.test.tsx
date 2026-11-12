import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/hooks/useTownSnapshot', () => ({
  useTownSnapshot: () => ({
    snapshot: {
      schema: 1, company_id: 'c', day: '2026-11-03', as_of: '2026-11-03T15:42:00+08:00', data_as_of: null, phase: 'day',
      today: { amount: '1000.00', invoice_count: 3, credit_note_count: 0, customer_count: 2, dealer_customer_count: 2 },
      shops: [], warehouses: [], reorder: { below_count: 4, set_count: 9 }, deliveries: { to_deliver: 2 },
      approvals: { total: 0, purchase_requests: 0, quotation_documents: 0 },
    },
    error: null,
    isLoading: false,
  }),
}));
vi.mock('next/dynamic', () => ({
  default: () => {
    const Scene = () => <div data-testid="town-scene" />;
    return Scene;
  },
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/town',
  useSearchParams: () => new URLSearchParams(),
}));

import { TownPage } from './TownPage';

afterEach(() => vi.restoreAllMocks());

describe('TownPage lightbox', () => {
  it('opens a dialog, not a side sheet, from the low stock card', () => {
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation((() => null) as never);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <TownPage />
      </QueryClientProvider>,
    );
    fireEvent.click(screen.getByText('What stock is low?'));
    expect(screen.getByRole('dialog')).toBeTruthy();
    expect(document.querySelector('[data-slot="sheet-content"]')).toBeNull();
  });
});
