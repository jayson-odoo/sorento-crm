/**
 * The themed PDF viewer: our toolbar over pdf.js canvases, replacing the browser's viewer.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { fakePdfJs } from '@/test-utils/fakePdfJs';

import { PdfViewer } from './PdfViewer';

vi.mock('@/components/common/pdf-viewer/pdfjs', async () =>
  (await import('@/test-utils/fakePdfJs')).fakePdfJsModule,
);

const toastError = vi.fn();
vi.mock('@/lib/toast', () => ({ toast: { error: (...a: unknown[]) => toastError(...a) } }));

beforeEach(() => {
  fakePdfJs.reset();
  toastError.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

async function ready() {
  await screen.findAllByRole('group', { name: /page 1$/ });
}

describe('PdfViewer', () => {
  it('draws every page under one toolbar and says where the reader is', async () => {
    fakePdfJs.setNumPages(3);
    render(<PdfViewer url="/files/po.pdf" title="Purchase order" />);

    await ready();
    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument();
    for (const n of [1, 2, 3]) {
      expect(screen.getByRole('group', { name: `Purchase order page ${n}` })).toBeInTheDocument();
    }
    // Never the browser's viewer.
    expect(document.querySelector('iframe, embed, object')).toBeNull();
    expect(fakePdfJs.getDocument).toHaveBeenCalledWith(
      expect.objectContaining({ url: '/files/po.pdf', isEvalSupported: false }),
    );
  });

  it('reads the bytes through loadData when given, not the cross-origin url', async () => {
    const loadData = vi.fn(async () => new Uint8Array([1, 2, 3]).buffer);
    render(
      <PdfViewer url="https://cdn.example.test/po.pdf?sig=1" loadData={loadData} title="PO" />,
    );

    await ready();
    expect(loadData).toHaveBeenCalledTimes(1);
    const params = fakePdfJs.getDocument.mock.calls[0][0] as { data?: Uint8Array; url?: string };
    expect(params.url).toBeUndefined();
    expect(Array.from(params.data ?? [])).toEqual([1, 2, 3]);
  });

  it('lays a text layer over each drawn page so text can be selected', async () => {
    render(<PdfViewer url="/files/po.pdf" title="PO" />);

    await ready();
    await waitFor(() => expect(fakePdfJs.textLayers.length).toBeGreaterThan(0));
    expect(fakePdfJs.textLayers[0].container).toHaveClass('textLayer');
  });

  it('destroys the pdf.js document task on unmount (PR #1256 review, kill K2)', async () => {
    const { unmount } = render(<PdfViewer url="/files/po.pdf" title="PO" />);

    await ready();
    const task = fakePdfJs.getDocument.mock.results.at(-1)?.value as { destroy: ReturnType<typeof vi.fn> };
    expect(task.destroy).not.toHaveBeenCalled();

    unmount();

    expect(task.destroy).toHaveBeenCalledTimes(1);
  });

  it('walks pages from the toolbar and stops at both ends', async () => {
    const onPageChange = vi.fn();
    fakePdfJs.setNumPages(2);
    render(<PdfViewer url="/files/po.pdf" title="PO" onPageChange={onPageChange} />);
    await ready();

    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
    expect(onPageChange).toHaveBeenCalledWith(2);
    expect(screen.getByText('Page 2 of 2')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled();
  });

  it('jumps to the page the caller asks for without echoing it back', async () => {
    const onPageChange = vi.fn();
    fakePdfJs.setNumPages(5);
    const { rerender } = render(
      <PdfViewer url="/files/po.pdf" title="PO" page={1} onPageChange={onPageChange} />,
    );
    await ready();

    rerender(<PdfViewer url="/files/po.pdf" title="PO" page={4} onPageChange={onPageChange} />);

    expect(screen.getByText('Page 4 of 5')).toBeInTheDocument();
    expect(onPageChange).not.toHaveBeenCalled();
  });

  it('scrolls the requested page to the top of the view, and reports the page scrolled to', async () => {
    const onPageChange = vi.fn();
    fakePdfJs.setNumPages(4);
    // jsdom does no layout: give each page a place in the column and the view a height.
    vi.spyOn(HTMLElement.prototype, 'offsetTop', 'get').mockImplementation(function (
      this: HTMLElement,
    ) {
      const n = Number(this.dataset.pageNumber ?? 0);
      return n ? 8 + (n - 1) * 808 : 0;
    });
    vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockImplementation(function (
      this: HTMLElement,
    ) {
      return this.dataset.pageNumber ? 800 : 0;
    });
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(600);
    const { rerender } = render(
      <PdfViewer url="/files/po.pdf" title="PO" page={1} onPageChange={onPageChange} />,
    );
    await ready();
    const region = screen.getByRole('region', { name: 'PO' });

    rerender(<PdfViewer url="/files/po.pdf" title="PO" page={3} onPageChange={onPageChange} />);
    expect(region.scrollTop).toBe(2 * 808);

    region.scrollTop = 808 + 100;
    fireEvent.scroll(region);
    await waitFor(() => expect(onPageChange).toHaveBeenLastCalledWith(2));
    expect(screen.getByText('Page 2 of 4')).toBeInTheDocument();
  });

  it('opens on the requested page and holds it inside the document', async () => {
    fakePdfJs.setNumPages(3);
    render(<PdfViewer url="/files/po.pdf" title="PO" page={99} pageCountHint={3} />);

    // The hint carries the count before the document has loaded.
    expect(await screen.findByText('Page 3 of 3')).toBeInTheDocument();
    await ready();
    expect(screen.getByText('Page 3 of 3')).toBeInTheDocument();
  });

  it('takes PageDown, PageUp, + and - from the keyboard, and keeps them from the page around it', async () => {
    const onPageChange = vi.fn();
    const outer = vi.fn();
    render(
      <div onKeyDown={outer}>
        <PdfViewer url="/files/po.pdf" title="PO" onPageChange={onPageChange} />
      </div>,
    );
    await ready();
    const region = screen.getByRole('region', { name: 'PO' });

    fireEvent.keyDown(region, { key: 'PageDown' });
    expect(onPageChange).toHaveBeenLastCalledWith(2);
    fireEvent.keyDown(region, { key: 'PageUp' });
    expect(onPageChange).toHaveBeenLastCalledWith(1);

    expect(screen.getByText('100%')).toBeInTheDocument();
    fireEvent.keyDown(region, { key: '+' });
    expect(screen.getByText('125%')).toBeInTheDocument();
    fireEvent.keyDown(region, { key: '-' });
    fireEvent.keyDown(region, { key: '-' });
    expect(screen.getByText('80%')).toBeInTheDocument();
    expect(outer).not.toHaveBeenCalled();
  });

  it('zooms from the toolbar and returns to fit width', async () => {
    render(<PdfViewer url="/files/po.pdf" title="PO" />);
    await ready();

    fireEvent.click(screen.getByRole('button', { name: 'Zoom in' }));
    expect(screen.getByText('125%')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fit width' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
    fireEvent.click(screen.getByRole('button', { name: 'Fit width' }));
    expect(screen.getByText('100%')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fit width' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('downloads the bytes it already holds, under the file name', async () => {
    const createObjectURL = vi.fn(() => 'blob:po');
    const revokeObjectURL = vi.fn();
    Object.assign(URL, { createObjectURL, revokeObjectURL });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    render(<PdfViewer url="/files/po.pdf" title="PO" fileName="PO-123.pdf" />);
    await ready();

    fireEvent.click(screen.getByRole('button', { name: 'Download' }));

    await waitFor(() => expect(click).toHaveBeenCalled());
    const anchor = click.mock.contexts[0] as HTMLAnchorElement;
    expect(anchor.download).toBe('PO-123.pdf');
    expect(createObjectURL).toHaveBeenCalled();
  });

  it('opens an http url in a new tab as a plain link', async () => {
    render(<PdfViewer url="https://cdn.example.test/po.pdf?sig=1" title="PO" />);
    await ready();

    expect(screen.getByRole('link', { name: 'Open in new tab' })).toHaveAttribute(
      'href',
      'https://cdn.example.test/po.pdf?sig=1',
    );
  });

  it('leaves Download and Open to the surrounding chrome when asked', async () => {
    render(<PdfViewer url="/files/po.pdf" title="PO" fileActions={false} />);
    await ready();

    expect(screen.queryByRole('button', { name: 'Download' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Open in new tab' })).toBeNull();
    expect(screen.queryByRole('link', { name: 'Open in new tab' })).toBeNull();
  });

  it('says the PDF could not be shown, and still offers the file, when it will not open', async () => {
    fakePdfJs.failNext();
    render(<PdfViewer url="https://cdn.example.test/po.pdf" title="PO" />);

    expect(await screen.findByText('This PDF could not be shown here')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open the file' })).toHaveAttribute(
      'href',
      'https://cdn.example.test/po.pdf',
    );
  });

  it('shows the not-available state when there is nothing to load', async () => {
    render(
      <PdfViewer
        url={null}
        title="PO"
        unavailable={<p>The scan is not available to preview</p>}
      />,
    );

    expect(await screen.findByText('The scan is not available to preview')).toBeInTheDocument();
    expect(fakePdfJs.getDocument).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'Download' })).toBeNull();
  });

  it('keeps the rendered document when only the signature on its url changes', async () => {
    const { rerender } = render(
      <PdfViewer url="https://cdn.example.test/po.pdf?sig=1" documentKey="v1" title="PO" />,
    );
    await ready();

    rerender(<PdfViewer url="https://cdn.example.test/other.pdf?sig=2" documentKey="v1" title="PO" />);

    await ready();
    expect(fakePdfJs.getDocument).toHaveBeenCalledTimes(1);
  });

  it('without a key, treats the url minus its signature as the document', async () => {
    const { rerender } = render(
      <PdfViewer url="https://cdn.example.test/po.pdf?sig=1" title="PO" />,
    );
    await ready();

    rerender(<PdfViewer url="https://cdn.example.test/po.pdf?sig=2" title="PO" />);
    await ready();
    expect(fakePdfJs.getDocument).toHaveBeenCalledTimes(1);

    rerender(<PdfViewer url="https://cdn.example.test/next.pdf?sig=3" title="PO" />);
    await waitFor(() => expect(fakePdfJs.getDocument).toHaveBeenCalledTimes(2));
  });

  it('shows a page-shaped skeleton while the document loads', async () => {
    let release: (b: ArrayBuffer) => void = () => {};
    const loadData = () => new Promise<ArrayBuffer>((resolve) => (release = resolve));
    render(<PdfViewer url={null} loadData={loadData} title="PO" />);

    const region = await screen.findByRole('region', { name: 'PO' });
    expect(within(region).getByRole('status', { name: 'Loading' })).toBeInTheDocument();
    release(new ArrayBuffer(4));
    await ready();
  });
});
