/**
 * The PDF viewer's search and zoom, driven the way a reader drives a normal PDF viewer:
 * Ctrl/Cmd+F, Enter / Shift+Enter, Esc, Ctrl/Cmd + '+' '-' '0', and Ctrl/Cmd + wheel (a
 * trackpad pinch arrives as ctrl+wheel). Owner hand test on PR #1256, 26 Sep 2026.
 */
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { fakePdfJs } from '@/test-utils/fakePdfJs';

import { PdfViewer } from './PdfViewer';

vi.mock(
  '@/components/common/pdf-viewer/pdfjs',
  async () => (await import('@/test-utils/fakePdfJs')).fakePdfJsModule,
);

vi.mock('@/lib/toast', () => ({ toast: { error: vi.fn() } }));

beforeEach(() => {
  fakePdfJs.reset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

const PADDING = 8;
const GAP = 8;

/**
 * jsdom does no layout. Lay the pages out the way the browser does: a column of pages, each
 * as tall and wide as its inline style, 8px apart inside 8px of padding, in a 600px-tall view.
 */
function fakeLayout() {
  const size = (el: HTMLElement, prop: 'width' | 'height') =>
    parseFloat(el.style[prop]) || 0;
  const pageNodes = () =>
    Array.from(document.querySelectorAll<HTMLElement>('[data-page-number]'));
  vi.spyOn(HTMLElement.prototype, 'offsetTop', 'get').mockImplementation(
    function (this: HTMLElement) {
      const n = Number(this.dataset.pageNumber ?? 0);
      if (!n) return 0;
      return pageNodes()
        .slice(0, n - 1)
        .reduce((top, node) => top + size(node, 'height') + GAP, PADDING);
    },
  );
  vi.spyOn(HTMLElement.prototype, 'offsetLeft', 'get').mockImplementation(
    function (this: HTMLElement) {
      return this.dataset.pageNumber ? PADDING : 0;
    },
  );
  vi.spyOn(HTMLElement.prototype, 'offsetHeight', 'get').mockImplementation(
    function (this: HTMLElement) {
      return this.dataset.pageNumber ? size(this, 'height') : 0;
    },
  );
  vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockImplementation(
    function (this: HTMLElement) {
      return this.dataset.pageNumber ? size(this, 'width') : 0;
    },
  );
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(600);
}

async function renderViewer(
  props: Partial<React.ComponentProps<typeof PdfViewer>> = {},
) {
  const outer = vi.fn();
  const utils = render(
    <div onKeyDown={outer}>
      <PdfViewer url="/files/quote.pdf" title="Quote" {...props} />
    </div>,
  );
  await screen.findAllByRole('group', { name: /page 1$/ });
  const region = screen.getByRole('region', { name: 'Quote' });
  return { ...utils, outer, region };
}

const zoomLabel = () => screen.getByTestId('pdf-viewer-zoom').textContent;

describe('PdfViewer search', () => {
  beforeEach(() => {
    fakePdfJs.setNumPages(3);
    fakePdfJs.setPageTexts([
      ['Sorento sofa, ', 'sorento chair'],
      ['Nothing to see'],
      ['Quotation for ', 'SORENTO'],
    ]);
  });

  it('opens on Ctrl+F and on Cmd+F with the box focused, instead of the browser find bar', async () => {
    const { region, outer } = await renderViewer();

    const notPrevented = fireEvent.keyDown(region, { key: 'f', ctrlKey: true });
    expect(notPrevented).toBe(false);
    const box = screen.getByRole('searchbox', { name: 'Search in PDF' });
    expect(box).toHaveFocus();
    expect(outer).not.toHaveBeenCalled();

    fireEvent.keyDown(box, { key: 'Escape' });
    expect(screen.queryByRole('searchbox')).toBeNull();

    fireEvent.keyDown(region, { key: 'F', metaKey: true });
    expect(
      screen.getByRole('searchbox', { name: 'Search in PDF' }),
    ).toHaveFocus();
  });

  it('opens from the toolbar too', async () => {
    await renderViewer();
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));
    expect(
      screen.getByRole('searchbox', { name: 'Search in PDF' }),
    ).toHaveFocus();
  });

  it('counts matches across every page and highlights them on the text layer', async () => {
    const { region } = await renderViewer();
    fireEvent.keyDown(region, { key: 'f', ctrlKey: true });

    fireEvent.change(screen.getByRole('searchbox'), {
      target: { value: 'sorento' },
    });

    expect(await screen.findByText('1 of 3')).toBeInTheDocument();
    await waitFor(() => {
      const marks = Array.from(
        region.querySelectorAll('.textLayer .highlight'),
      );
      // Page 1 is drawn: both of its matches are painted, the first one selected.
      expect(marks.map((m) => m.textContent)).toEqual(
        expect.arrayContaining(['Sorento', 'sorento']),
      );
      expect(
        region.querySelectorAll('.textLayer .highlight.selected'),
      ).toHaveLength(1);
      expect(
        region.querySelector('.textLayer .highlight.selected')?.textContent,
      ).toBe('Sorento');
    });
  });

  it('steps with Enter and Shift+Enter and the arrow buttons, wrapping at both ends', async () => {
    const { region } = await renderViewer();
    fireEvent.keyDown(region, { key: 'f', ctrlKey: true });
    const box = screen.getByRole('searchbox');
    fireEvent.change(box, { target: { value: 'sorento' } });
    await screen.findByText('1 of 3');

    fireEvent.keyDown(box, { key: 'Enter' });
    expect(screen.getByText('2 of 3')).toBeInTheDocument();
    fireEvent.keyDown(box, { key: 'Enter' });
    expect(screen.getByText('3 of 3')).toBeInTheDocument();
    fireEvent.keyDown(box, { key: 'Enter' });
    expect(screen.getByText('1 of 3')).toBeInTheDocument();
    fireEvent.keyDown(box, { key: 'Enter', shiftKey: true });
    expect(screen.getByText('3 of 3')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Previous match' }));
    expect(screen.getByText('2 of 3')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Next match' }));
    expect(screen.getByText('3 of 3')).toBeInTheDocument();
  });

  it('scrolls to the page of the match it moves to, and reports that page', async () => {
    fakeLayout();
    const onPageChange = vi.fn();
    const { region } = await renderViewer({ onPageChange });
    fireEvent.keyDown(region, { key: 'f', ctrlKey: true });
    const box = screen.getByRole('searchbox');
    fireEvent.change(box, { target: { value: 'sorento' } });
    await screen.findByText('1 of 3');

    fireEvent.keyDown(box, { key: 'Enter', shiftKey: true });

    expect(screen.getByText('3 of 3')).toBeInTheDocument();
    const page3 = screen.getByRole('group', { name: 'Quote page 3' });
    expect(region.scrollTop).toBe(page3.offsetTop - PADDING);
    await waitFor(() => expect(onPageChange).toHaveBeenLastCalledWith(3));
    // A browser fires scroll for that jump; jsdom does not. It is what draws page 3.
    fireEvent.scroll(region);
    await waitFor(() =>
      expect(
        page3.querySelector('.textLayer .highlight.selected')?.textContent,
      ).toBe('SORENTO'),
    );
  });

  it('says so when nothing matches', async () => {
    const { region } = await renderViewer();
    fireEvent.keyDown(region, { key: 'f', ctrlKey: true });
    fireEvent.change(screen.getByRole('searchbox'), {
      target: { value: 'wardrobe' },
    });

    expect(await screen.findByText('0 of 0')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next match' })).toBeDisabled();
  });

  it('closes on Esc, clears the highlights and hands focus back to the pages', async () => {
    const { region } = await renderViewer();
    fireEvent.keyDown(region, { key: 'f', ctrlKey: true });
    const box = screen.getByRole('searchbox');
    fireEvent.change(box, { target: { value: 'sorento' } });
    await screen.findByText('1 of 3');
    await waitFor(() =>
      expect(region.querySelector('.highlight')).not.toBeNull(),
    );

    fireEvent.keyDown(box, { key: 'Escape' });

    expect(screen.queryByRole('searchbox')).toBeNull();
    expect(region.querySelector('.highlight')).toBeNull();
    expect(region).toHaveFocus();
  });

  it('keeps Esc from closing a dialog around it while the search is open', async () => {
    // Radix dialogs listen for Escape on the document in the capture phase.
    const dialogEscape = vi.fn();
    document.addEventListener('keydown', dialogEscape, true);
    try {
      const { region } = await renderViewer();
      fireEvent.keyDown(region, { key: 'f', ctrlKey: true });

      fireEvent.keyDown(screen.getByRole('searchbox'), { key: 'Escape' });

      expect(screen.queryByRole('searchbox')).toBeNull();
      expect(dialogEscape).not.toHaveBeenCalledWith(
        expect.objectContaining({ key: 'Escape' }),
      );

      // With the search closed, Esc is the dialog's again.
      fireEvent.keyDown(region, { key: 'Escape' });
      expect(dialogEscape).toHaveBeenCalledWith(
        expect.objectContaining({ key: 'Escape' }),
      );
    } finally {
      document.removeEventListener('keydown', dialogEscape, true);
    }
  });

  it('types + and - into the box rather than zooming', async () => {
    const { region } = await renderViewer();
    const before = zoomLabel();
    fireEvent.keyDown(region, { key: 'f', ctrlKey: true });

    const notPrevented = fireEvent.keyDown(screen.getByRole('searchbox'), {
      key: '+',
    });

    expect(notPrevented).toBe(true);
    expect(zoomLabel()).toBe(before);
  });

  it('says a scan has no searchable text', async () => {
    fakePdfJs.setPageTexts([]);
    const { region } = await renderViewer();
    fireEvent.keyDown(region, { key: 'f', ctrlKey: true });

    expect(
      await screen.findByText('No searchable text in this PDF'),
    ).toBeInTheDocument();
  });
});

describe('PdfViewer zoom', () => {
  it('zooms in, out and back to fit width on Ctrl or Cmd with +, - and 0', async () => {
    const { region, outer } = await renderViewer();
    expect(zoomLabel()).toBe('100%');

    expect(fireEvent.keyDown(region, { key: '+', ctrlKey: true })).toBe(false);
    expect(zoomLabel()).toBe('125%');
    // Ctrl and the = key (the unshifted +) is what most keyboards send.
    fireEvent.keyDown(region, { key: '=', metaKey: true });
    expect(zoomLabel()).toBe('156%');
    fireEvent.keyDown(region, { key: '-', ctrlKey: true });
    expect(zoomLabel()).toBe('125%');
    expect(screen.getByRole('button', { name: 'Fit width' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );

    expect(fireEvent.keyDown(region, { key: '0', ctrlKey: true })).toBe(false);
    expect(zoomLabel()).toBe('100%');
    expect(screen.getByRole('button', { name: 'Fit width' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(outer).not.toHaveBeenCalled();
  });

  it('zooms on Ctrl + wheel (and a trackpad pinch), and leaves a plain wheel to scroll', async () => {
    const { region } = await renderViewer();

    const plain = new WheelEvent('wheel', {
      deltaY: 100,
      bubbles: true,
      cancelable: true,
    });
    act(() => {
      region.dispatchEvent(plain);
    });
    expect(plain.defaultPrevented).toBe(false);
    expect(zoomLabel()).toBe('100%');

    const zoomIn = new WheelEvent('wheel', {
      deltaY: -100,
      ctrlKey: true,
      bubbles: true,
      cancelable: true,
    });
    act(() => {
      region.dispatchEvent(zoomIn);
    });
    expect(zoomIn.defaultPrevented).toBe(true);
    expect(zoomLabel()).toBe('122%');

    act(() => {
      region.dispatchEvent(
        new WheelEvent('wheel', {
          deltaY: 100,
          metaKey: true,
          bubbles: true,
          cancelable: true,
        }),
      );
    });
    expect(zoomLabel()).toBe('100%');
  });

  it('keeps the point under the cursor in place across a wheel zoom', async () => {
    fakeLayout();
    fakePdfJs.setNumPages(4);
    const { region } = await renderViewer();
    // jsdom: the scroller sits at the viewport origin, so clientX/Y are inside it.
    region.scrollTop = 1000;
    const cursor = { x: 300, y: 200 };
    const pages = () =>
      screen.getAllByRole('group', { name: /Quote page \d$/ });
    // The document point under the cursor: page 2 (816..1616), 384px down it at 100%.
    const before = { page: 2, y: 1000 + cursor.y - pages()[1].offsetTop };
    expect(before.y).toBe(384);

    act(() => {
      region.dispatchEvent(
        new WheelEvent('wheel', {
          deltaY: -100,
          ctrlKey: true,
          clientX: cursor.x,
          clientY: cursor.y,
          bubbles: true,
          cancelable: true,
        }),
      );
    });

    expect(zoomLabel()).toBe('122%');
    const scale = 1.22;
    const page2 = pages()[1];
    // Same spot on page 2, scaled, still under the cursor.
    expect(region.scrollTop + cursor.y - page2.offsetTop).toBeCloseTo(
      before.y * scale,
      0,
    );
  });

  it('re-draws the pages at the new scale rather than stretching them', async () => {
    await renderViewer();
    const page1 = screen.getByRole('group', { name: 'Quote page 1' });
    expect(page1.style.width).toBe('600px');

    fireEvent.click(screen.getByRole('button', { name: 'Zoom in' }));

    expect(page1.style.width).toBe('750px');
    expect(page1.style.transform).toBe('');
  });
});
