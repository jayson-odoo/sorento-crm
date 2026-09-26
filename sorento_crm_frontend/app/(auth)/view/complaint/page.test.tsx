/**
 * PR #1256 review, blocking finding 1: this page builds preview items from
 * `file_url` alone (a signed, cross-origin storage URL with no CORS headers) and
 * passed no byte route, so pdf.js could not read it and every attachment landed on
 * "This PDF could not be shown here". The fix wires each attachment's `attachment_id`
 * into the same-origin byte route (`attachmentDownload.ts`) so the modal loads bytes
 * through `fetchBytes` instead of fetching the raw CDN url.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import { fakePdfJs } from '@/test-utils/fakePdfJs';

vi.mock('@/components/common/pdf-viewer/pdfjs', async () =>
  (await import('@/test-utils/fakePdfJs')).fakePdfJsModule,
);

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams({ token: 'tok-1' }),
}));

import ViewComplaintPage from './page';

const CDN_URL = 'https://cdn.example.com/complaint-scan.pdf';

function summaryWithAttachment() {
  return {
    entity_type: 'complaint',
    entity_id: 'complaint-1',
    attachments: [
      {
        id: 'link-1',
        attachment_id: 'att-1',
        original_filename: 'complaint-scan.pdf',
        file_url: CDN_URL,
        uploader_kind: 'contact',
      },
    ],
  };
}

describe('public complaint view - url-only PDF attachment', () => {
  beforeEach(() => {
    fakePdfJs.reset();
  });

  it('previews the PDF through the same-origin byte route, never fetching the cross-origin CDN url', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/v1/public/view/complaint?')) {
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

    render(<ViewComplaintPage />);

    fireEvent.click(await screen.findByText('complaint-scan.pdf'));

    // Drawn in the themed viewer, not stuck on the CORS error state.
    expect(await screen.findByRole('group', { name: 'complaint-scan.pdf page 1' })).toBeInTheDocument();
    expect(screen.queryByText('This PDF could not be shown here')).not.toBeInTheDocument();

    // The byte route was fetched, keyed on attachment_id and carrying the token -
    // never the raw cross-origin CDN url.
    await waitFor(() => {
      const calledUrls = fetchMock.mock.calls.map((call) => String(call[0]));
      expect(calledUrls).not.toContain(CDN_URL);
      expect(
        calledUrls.some((url) =>
          url.match(/\/api\/v1\/public\/view\/complaint\/attachments\/att-1\/download\?token=tok-1$/),
        ),
      ).toBe(true);
    });
    // pdf.js itself never saw the cross-origin CDN url as a fetch source.
    const sources = fakePdfJs.getDocument.mock.calls.map((call) => call[0]);
    expect(sources.every((source) => !('url' in source) || source.url !== CDN_URL)).toBe(true);
    expect(sources.some((source) => 'data' in source)).toBe(true);

    vi.unstubAllGlobals();
  });
});
