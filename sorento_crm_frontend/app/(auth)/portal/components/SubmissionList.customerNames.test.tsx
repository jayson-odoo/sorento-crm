/**
 * PRICETAG-REQUEST-LAYOUT (crew view-as pass, 11 Nov): a price tag request for several customers
 * reads "First +1" on the salesperson's own list, and hovering it shows EVERY customer name, on
 * the board cards and in the list view, same as the staff list.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render as rtlRender, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
  usePathname: () => '/portal',
}));

const ROW = {
  id: 'req-1',
  kind: 'price_tag_request' as const,
  title: 'ZZT Construction Sdn Bhd +1',
  document_number: 'PT-ZZT-0006',
  reference: null,
  status: 'approved',
  is_editable: false,
  is_draft: false,
  created_at: '2026-11-11T00:00:00Z',
  customer_name: 'ZZT Construction Sdn Bhd +1',
  customer_names: 'ZZT Construction Sdn Bhd, ZZT Bath Studio',
  needed_by_date: null,
};

vi.mock('../lib/price-tag-request-service', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  listRequestsAsSummaries: vi.fn(async () => [ROW]),
}));

import { KindSubmissionList } from './SubmissionList';
import { makePriceTagRequestService } from '../lib/price-tag-request-service';

function render(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtlRender(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  window.localStorage.clear();
});

describe('salesperson list: every customer on hover', () => {
  it('board card', async () => {
    window.localStorage.setItem('sorento.portalView', 'board');
    render(<KindSubmissionList kind="price_tag_request" canCreate={false} />);
    const shown = await screen.findByText('ZZT Construction Sdn Bhd +1', { selector: 'p, p *' });
    expect(shown.closest('[title]')).toHaveAttribute(
      'title',
      'ZZT Construction Sdn Bhd, ZZT Bath Studio',
    );
  });

  it('list view cell', async () => {
    window.localStorage.setItem('sorento.portalView', 'list');
    render(<KindSubmissionList kind="price_tag_request" canCreate={false} />);
    const cell = await screen.findByText('ZZT Construction Sdn Bhd +1', { selector: 'span' });
    expect(cell).toHaveAttribute('title', 'ZZT Construction Sdn Bhd, ZZT Bath Studio');
  });
});

describe('the summary mapping carries every name', () => {
  it('customer_name is "First +N", customer_names lists them all', async () => {
    const fetcher = vi.fn(async () =>
      new Response(
        JSON.stringify({
          items: [
            {
              id: 'req-1',
              doc_number: 'PT-ZZT-0006',
              debtor_code: 'ZZT-C1',
              debtor_name: 'ZZT Construction Sdn Bhd',
              customers: [
                { code: 'ZZT-C1', name: 'ZZT Construction Sdn Bhd' },
                { code: 'ZZT-C3', name: 'ZZT Bath Studio' },
              ],
              needed_by_date: null,
              notes: null,
              status: 'approved',
              line_count: 1,
              created_at: '2026-11-11T00:00:00Z',
              portal_draft_at: null,
            },
          ],
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    const service = makePriceTagRequestService(fetcher as never);
    const [row] = await service.listRequestsAsSummaries();
    expect(row.customer_name).toBe('ZZT Construction Sdn Bhd +1');
    expect(row.customer_names).toBe('ZZT Construction Sdn Bhd, ZZT Bath Studio');
  });
});
