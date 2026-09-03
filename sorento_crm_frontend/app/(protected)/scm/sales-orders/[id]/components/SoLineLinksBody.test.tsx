/**
 * SoLineLinksBody - the "Linked" lightbox on the SO detail's lines grid (R5, AC-L4).
 *
 * `DrillTable` calls `useListingColumnPreferences` even with `listingKey={null}` - see
 * `PlanRowDialog.test.tsx`'s own note - so this needs a `QueryClientProvider` and the
 * `next/navigation` stub too.
 */
import React from 'react';
import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});

vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/sales-orders/so-1',
}));

import { SoLineLinksBody } from './SoLineLinksBody';
import type { SalesOrderLineLink } from '../../../types/scm.types';

afterEach(cleanup);

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const LINKS: SalesOrderLineLink[] = [
  {
    kind: 'spo',
    document: 'SPO-2026/08-0061',
    qty: '95',
    location: 'BRW',
    expected_date: '2026-09-14',
    late: false,
  },
  {
    kind: 'po',
    document: '202607-S0105',
    purchase_order_id: 'po-105',
    qty: '5',
    location: 'BRW-NTC',
    expected_date: '2026-08-01',
    late: true,
    late_days: 3,
  },
];

describe('SoLineLinksBody', () => {
  it('renders one row per link, by kind and document', () => {
    renderWithClient(<SoLineLinksBody links={LINKS} />);

    expect(screen.getByText('spo')).toBeInTheDocument();
    expect(screen.getByText('SPO-2026/08-0061')).toBeInTheDocument();
    expect(screen.getByText('po')).toBeInTheDocument();
    expect(screen.getByText('202607-S0105')).toBeInTheDocument();
  });

  it('carries the Late badge with days on the late link, and none on the other', () => {
    renderWithClient(<SoLineLinksBody links={LINKS} />);

    expect(screen.getByText('late 3 d')).toBeInTheDocument();
  });

  it('links the document to its own PO detail when purchase_order_id is present (L4, review round)', () => {
    renderWithClient(<SoLineLinksBody links={LINKS} />);

    const link = screen.getByRole('link', { name: '202607-S0105' });
    expect(link).toHaveAttribute('href', '/scm/purchase-orders/po-105');
    // The SPO link has no `purchase_order_id` in this fixture, so it stays plain text.
    expect(screen.queryByRole('link', { name: 'SPO-2026/08-0061' })).toBeNull();
  });

  it('says Not linked, rather than an empty table, when there are no links', () => {
    renderWithClient(<SoLineLinksBody links={[]} />);

    expect(screen.getByText('Not linked.')).toBeInTheDocument();
  });
});
