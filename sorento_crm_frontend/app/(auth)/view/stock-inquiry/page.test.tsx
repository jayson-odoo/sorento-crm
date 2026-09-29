/**
 * Same regression as the complaint view (PR #1256 review, blocking finding 1):
 * this page also built preview items from `file_url` alone, with no byte route, so
 * a cross-origin scan landed on the viewer's CORS error state. See
 * `../complaint/page.test.tsx` for the fuller narrative; this covers the second
 * call site the review named.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';

import { fakePdfJs } from '@/test-utils/fakePdfJs';

vi.mock('@/components/common/pdf-viewer/pdfjs', async () =>
  (await import('@/test-utils/fakePdfJs')).fakePdfJsModule,
);

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams({ token: 'tok-1' }),
}));

import ViewStockInquiryPage from './page';

const CDN_URL = 'https://cdn.example.com/inquiry-scan.pdf';

function summaryWithAttachment() {
  return {
    entity_type: 'stock_inquiry',
    entity_id: 'inquiry-1',
    attachments: [
      {
        id: 'link-1',
        attachment_id: 'att-1',
        original_filename: 'inquiry-scan.pdf',
        file_url: CDN_URL,
        uploader_kind: 'contact',
      },
    ],
  };
}

describe('public stock inquiry view - url-only PDF attachment', () => {
  beforeEach(() => {
    fakePdfJs.reset();
  });

  it('previews the PDF through the same-origin byte route, never fetching the cross-origin CDN url', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/v1/public/view/stock-inquiry?')) {
        return Promise.resolve({
          ok: true,
          json: async () => summaryWithAttachment(),
        } as Response);
      }
      if (url.includes('/attachments/att-1/download')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          arrayBuffer: async () => new ArrayBuffer(4),
        } as Response);
      }
      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<ViewStockInquiryPage />);

    fireEvent.click(await screen.findByText('inquiry-scan.pdf'));

    expect(await screen.findByRole('group', { name: 'inquiry-scan.pdf page 1' })).toBeInTheDocument();
    expect(screen.queryByText('This PDF could not be shown here')).not.toBeInTheDocument();

    await waitFor(() => {
      const calledUrls = fetchMock.mock.calls.map((call) => String(call[0]));
      expect(calledUrls).not.toContain(CDN_URL);
      expect(
        calledUrls.some((url) =>
          url.match(/\/api\/v1\/public\/view\/stock-inquiry\/attachments\/att-1\/download\?token=tok-1$/),
        ),
      ).toBe(true);
    });

    vi.unstubAllGlobals();
  });
});
