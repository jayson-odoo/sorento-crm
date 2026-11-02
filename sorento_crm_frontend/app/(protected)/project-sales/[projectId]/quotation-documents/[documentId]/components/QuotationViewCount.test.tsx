import * as React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { QuotationViewCount, viewCountText } from './QuotationViewCount';
import type { QuotationDocument } from '../../../../_shared/services/quotationDocumentService';

const listQuotationViews = vi.fn();
vi.mock(
  '../../../../_shared/services/quotationDocumentService',
  async (importOriginal) => {
    const actual = await importOriginal<Record<string, unknown>>();
    return {
      ...actual,
      listQuotationViews: (...args: unknown[]) => listQuotationViews(...args),
    };
  },
);

function doc(patch: Partial<QuotationDocument>): QuotationDocument {
  return {
    id: 'doc-1',
    is_issued: true,
    view_count: 0,
    last_viewed_at: null,
    ...patch,
  } as QuotationDocument;
}

function renderIt(document: QuotationDocument) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <QuotationViewCount projectId="p-1" document={document} />
    </QueryClientProvider>,
  );
}

describe('viewCountText', () => {
  it('says not viewed yet with no views', () => {
    expect(viewCountText({ view_count: 0, last_viewed_at: null })).toBe(
      'Not viewed yet',
    );
  });
  it('says one time in the singular, in Malaysia time', () => {
    expect(
      viewCountText({ view_count: 1, last_viewed_at: '2026-11-02T13:41:00' }),
    ).toBe('Viewed 1 time, last 02/11/2026, 9:41 pm');
  });
  it('counts plural', () => {
    expect(
      viewCountText({ view_count: 3, last_viewed_at: '2026-11-02T13:41:00' }),
    ).toMatch(/^Viewed 3 times, last /);
  });
});

describe('QuotationViewCount', () => {
  it('renders nothing before the first issue', () => {
    const { container } = renderIt(doc({ is_issued: false }));
    expect(container).toBeEmptyDOMElement();
  });

  it('opens the view log, newest first, with revision and device', async () => {
    listQuotationViews.mockResolvedValue([
      {
        id: 'v2',
        viewed_at: '2026-11-02T14:05:00',
        issue_no: 2,
        our_ref: 'PRJQ-2026-0003-R2',
        device: 'desktop',
      },
      {
        id: 'v1',
        viewed_at: '2026-11-02T13:05:00',
        issue_no: 1,
        our_ref: 'PRJQ-2026-0003-R1',
        device: 'mobile',
      },
    ]);
    renderIt(doc({ view_count: 1, last_viewed_at: '2026-11-02T14:05:00' }));
    fireEvent.click(screen.getByTestId('quotation-view-count'));
    const items = await screen.findAllByRole('listitem');
    expect(items).toHaveLength(2);
    expect(items[0].textContent).toContain('PRJQ-2026-0003-R2');
    expect(items[0].textContent).toContain('Computer');
    expect(items[1].textContent).toContain('Phone');
    expect(listQuotationViews).toHaveBeenCalledWith('p-1', 'doc-1');
  });

  it('shows an empty state with no views', async () => {
    listQuotationViews.mockResolvedValue([]);
    renderIt(doc({}));
    fireEvent.click(screen.getByTestId('quotation-view-count'));
    expect(await screen.findByText('No views yet')).toBeInTheDocument();
  });
});
