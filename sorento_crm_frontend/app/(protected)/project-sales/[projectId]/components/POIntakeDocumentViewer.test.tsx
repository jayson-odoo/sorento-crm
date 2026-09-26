/**
 * P4 - the page beside the extraction.
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fakePdfJs } from '@/test-utils/fakePdfJs';
import { POIntakeDocumentViewer } from './POIntakeDocumentViewer';

vi.mock('@/components/common/pdf-viewer/pdfjs', async () =>
  (await import('@/test-utils/fakePdfJs')).fakePdfJsModule,
);

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));

const onPageChange = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  fakePdfJs.reset();
});

describe('POIntakeDocumentViewer', () => {
  it('renders the requested page of a PDF in the themed viewer, with one page bar', async () => {
    fakePdfJs.setNumPages(10);
    render(
      <POIntakeDocumentViewer
        documentUrl="https://example.test/po.pdf"
        pageCount={10}
        page={4}
        onPageChange={onPageChange}
      />,
    );

    expect(await screen.findByRole('group', { name: 'Purchase order page 4' })).toBeInTheDocument();
    expect(screen.getAllByText('Page 4 of 10')).toHaveLength(1);
    expect(screen.getAllByRole('button', { name: 'Next page' })).toHaveLength(1);
    expect(document.querySelector('iframe')).toBeNull();
  });

  it('reads the scan through the authenticated download route when it knows the attachment', async () => {
    apiFetch.mockResolvedValue({ ok: true, arrayBuffer: async () => new ArrayBuffer(4) });
    render(
      <POIntakeDocumentViewer
        documentUrl="https://cdn.example.test/po.pdf?sig=abc"
        attachmentId="att-9"
        pageCount={3}
        page={1}
        onPageChange={onPageChange}
      />,
    );

    await screen.findByRole('group', { name: 'Purchase order page 1' });
    expect(apiFetch).toHaveBeenCalledWith('/api/v1/resource-management/attachments/att-9/download');
    expect(fakePdfJs.getDocument.mock.calls[0][0]).not.toHaveProperty('url');
    // Open still goes to the file itself.
    expect(screen.getByRole('link', { name: 'Open in new tab' })).toHaveAttribute(
      'href',
      'https://cdn.example.test/po.pdf?sig=abc',
    );
  });

  it('walks pages and stops at both ends', async () => {
    fakePdfJs.setNumPages(10);
    const { rerender } = render(
      <POIntakeDocumentViewer
        documentUrl="https://example.test/po.pdf"
        pageCount={10}
        page={1}
        onPageChange={onPageChange}
      />,
    );
    await screen.findByRole('group', { name: 'Purchase order page 1' });

    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
    expect(onPageChange).toHaveBeenCalledWith(2);

    rerender(
      <POIntakeDocumentViewer
        documentUrl="https://example.test/po.pdf"
        pageCount={10}
        page={10}
        onPageChange={onPageChange}
      />,
    );
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled();
  });

  it('holds a page number inside the document rather than trusting the caller', async () => {
    fakePdfJs.setNumPages(3);
    render(
      <POIntakeDocumentViewer
        documentUrl="https://example.test/po.pdf"
        pageCount={3}
        page={99}
        onPageChange={onPageChange}
      />,
    );

    expect(await screen.findByText('Page 3 of 3')).toBeInTheDocument();
  });

  it('renders a photographed PO as an image, not the PDF viewer', () => {
    render(
      <POIntakeDocumentViewer
        documentUrl="https://example.test/po.jpg?signature=abc"
        pageCount={1}
        page={1}
        onPageChange={onPageChange}
      />,
    );

    expect(screen.getByRole('img', { name: 'Purchase order page 1' })).toBeInTheDocument();
  });

  it('says the scan is not available rather than showing a broken frame', () => {
    render(
      <POIntakeDocumentViewer
        documentUrl={null}
        pageCount={10}
        page={1}
        onPageChange={onPageChange}
      />,
    );

    expect(screen.getByText(/The scan is not available to preview/i)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Open the file/i })).toBeNull();
  });
});
