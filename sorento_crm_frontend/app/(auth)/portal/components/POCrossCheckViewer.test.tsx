/**
 * PLAN-price-tag-feedback-r2 review fix: a pre-fix row (uploaded before the
 * portal upload route passed `content_type` through) or any other legacy row
 * with a NULL mime_type must still classify as PDF/image by filename
 * extension, same as AttachmentDropzone's isImageAttachment/isVideoAttachment.
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import POCrossCheckViewer from './POCrossCheckViewer';
import type { PortalAttachment } from '../lib/portal-client';

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
  it('renders a NULL-content-type .pdf row as an iframe, by filename extension', () => {
    render(
      <POCrossCheckViewer
        attachments={[attachment({ filename: 'ZZT-po.pdf', content_type: null })]}
        lines={[]}
      />,
    );

    const frame = document.querySelector('iframe');
    expect(frame).not.toBeNull();
    expect(frame?.getAttribute('title')).toBe('ZZT-po.pdf');
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

    expect(document.querySelector('iframe')).toBeNull();
    expect(document.querySelector('img')).toBeNull();
    expect(screen.getByText('ZZT-notes.txt')).toBeInTheDocument();
  });

  it('shows the empty state with no attachments', () => {
    render(<POCrossCheckViewer attachments={[]} lines={[]} />);

    expect(screen.getByText('No PO attached to this request.')).toBeInTheDocument();
  });
});
