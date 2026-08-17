/**
 * P4 - the page beside the extraction.
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { POIntakeDocumentViewer } from './POIntakeDocumentViewer';

const onPageChange = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
});

describe('POIntakeDocumentViewer', () => {
  it('renders the requested page of a PDF and says where it is', () => {
    render(
      <POIntakeDocumentViewer
        documentUrl="https://example.test/po.pdf"
        pageCount={10}
        page={4}
        onPageChange={onPageChange}
      />,
    );

    expect(screen.getByText('Page 4 of 10')).toBeInTheDocument();
    expect(screen.getByTitle('Purchase order page 4')).toHaveAttribute(
      'src',
      'https://example.test/po.pdf#page=4&view=FitH',
    );
  });

  it('walks pages and stops at both ends', () => {
    const { rerender } = render(
      <POIntakeDocumentViewer
        documentUrl="https://example.test/po.pdf"
        pageCount={10}
        page={1}
        onPageChange={onPageChange}
      />,
    );

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

  it('holds a page number inside the document rather than trusting the caller', () => {
    render(
      <POIntakeDocumentViewer
        documentUrl="https://example.test/po.pdf"
        pageCount={3}
        page={99}
        onPageChange={onPageChange}
      />,
    );

    expect(screen.getByText('Page 3 of 3')).toBeInTheDocument();
  });

  it('renders a photographed PO as an image, not an iframe', () => {
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
