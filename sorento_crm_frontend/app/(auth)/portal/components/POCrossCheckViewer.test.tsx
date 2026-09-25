/**
 * PLAN-price-tag-feedback-r2 review fix: a pre-fix row (uploaded before the
 * portal upload route passed `content_type` through) or any other legacy row
 * with a NULL mime_type must still classify as PDF/image by filename
 * extension, same as AttachmentDropzone's isImageAttachment/isVideoAttachment.
 */
import { beforeEach, describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { fakePdfJs } from '@/test-utils/fakePdfJs';
import POCrossCheckViewer from './POCrossCheckViewer';
import type { PortalAttachment } from '../lib/portal-client';

vi.mock('@/components/common/pdf-viewer/pdfjs', async () =>
  (await import('@/test-utils/fakePdfJs')).fakePdfJsModule,
);

const fetchPortalAttachmentBytes = vi.fn();
vi.mock('../lib/portal-client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/portal-client')>()),
  fetchPortalAttachmentBytes: (url: string) => fetchPortalAttachmentBytes(url),
}));

beforeEach(() => {
  fakePdfJs.reset();
  fetchPortalAttachmentBytes.mockReset();
  fetchPortalAttachmentBytes.mockResolvedValue({
    ok: true,
    arrayBuffer: async () => new ArrayBuffer(4),
  });
});

function attachment(overrides: Partial<PortalAttachment> = {}): PortalAttachment {
  return {
    link_id: 'link-1',
    attachment_id: 'att-1',
    filename: 'zzt-po.pdf',
    size: 1024,
    url: 'https://cdn.test/zzt-po.pdf',
    content_type: null,
    ...overrides,
  };
}

describe('POCrossCheckViewer attachment classification', () => {
  it('renders a NULL-content-type .pdf row in the PDF viewer, by filename extension', async () => {
    render(
      <POCrossCheckViewer
        attachments={[attachment({ filename: 'ZZT-po.pdf', content_type: null })]}
        lines={[]}
      />,
    );

    expect(await screen.findByRole('group', { name: 'ZZT-po.pdf page 1' })).toBeInTheDocument();
    expect(document.querySelector('iframe')).toBeNull();
    // The signed url is cross-origin; the bytes come through the portal token route.
    expect(fetchPortalAttachmentBytes).toHaveBeenCalledWith(
      '/api/v1/public/portal/attachments/att-1/download',
    );
  });

  it('renders a NULL-content-type image row as an img, by filename extension', () => {
    render(
      <POCrossCheckViewer
        attachments={[attachment({ filename: 'ZZT-po.jpg', content_type: null })]}
        lines={[]}
      />,
    );

    const img = document.querySelector('img');
    expect(img).not.toBeNull();
    expect(img?.getAttribute('alt')).toBe('ZZT-po.jpg');
  });

  it('falls back to the generic file row for an unrecognised extension', () => {
    render(
      <POCrossCheckViewer
        attachments={[attachment({ filename: 'ZZT-notes.txt', content_type: null })]}
        lines={[]}
      />,
    );

    expect(document.querySelector('[data-slot="pdf-viewer"]')).toBeNull();
    expect(document.querySelector('img')).toBeNull();
    expect(screen.getByText('ZZT-notes.txt')).toBeInTheDocument();
  });

  it('shows the empty state with no attachments', () => {
    render(<POCrossCheckViewer attachments={[]} lines={[]} />);

    expect(
      screen.getByText('No sales order files attached to this request.'),
    ).toBeInTheDocument();
  });
});
