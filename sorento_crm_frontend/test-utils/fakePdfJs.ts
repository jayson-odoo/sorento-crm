import { vi } from 'vitest';

/**
 * A stand-in for pdf.js, for tests that render the real `PdfViewer`.
 *
 * jsdom has no canvas and no worker, so the library itself cannot run. Mock the viewer's
 * one import point with the shared instance, and reset it per test:
 *
 *   vi.mock('@/components/common/pdf-viewer/pdfjs', async () =>
 *     (await import('@/test-utils/fakePdfJs')).fakePdfJsModule);
 *   beforeEach(() => fakePdfJs.reset());
 */
export interface FakePdfJs {
  load: () => Promise<unknown>;
  getDocument: ReturnType<typeof vi.fn>;
  textLayers: { container: HTMLElement }[];
  /** Text items on each page of the next document (page 1 first); pages past the list have none. */
  setPageTexts: (pages: string[][]) => void;
  /** Pages the next document opens with. */
  setNumPages: (n: number) => void;
  /** The next document fails to open. */
  failNext: () => void;
  bytes: Uint8Array;
  reset: () => void;
}

export function createFakePdfJs(): FakePdfJs {
  let numPages = 3;
  let fail = false;
  let pageTexts: string[][] = [];
  const bytes = new Uint8Array([37, 80, 68, 70]);
  const textLayers: { container: HTMLElement }[] = [];

  const page = (pageNumber: number, texts: string[][]) => {
    const textContent = () => ({
      items: (texts[pageNumber - 1] ?? []).map((str) => ({
        str,
        hasEOL: false,
      })),
    });
    return {
      pageNumber,
      userUnit: 1,
      getViewport: ({ scale }: { scale: number }) => ({
        width: 600 * scale,
        height: 800 * scale,
        scale,
      }),
      render: vi.fn(() => ({ promise: Promise.resolve(), cancel: vi.fn() })),
      // The real one is a stream; the fake TextLayer below reads the items straight off it.
      streamTextContent: vi.fn(textContent),
      getTextContent: vi.fn(async () => textContent()),
    };
  };

  /** Draws one span per text item, the way pdf.js does, and exposes the same two getters. */
  class TextLayer {
    textDivs: HTMLElement[] = [];
    textContentItemsStr: string[] = [];
    private options: {
      container: HTMLElement;
      textContentSource: { items?: { str: string }[] };
    };
    constructor(options: {
      container: HTMLElement;
      textContentSource: { items?: { str: string }[] };
    }) {
      this.options = options;
      textLayers.push(options);
    }
    render() {
      for (const { str } of this.options.textContentSource.items ?? []) {
        const span = document.createElement('span');
        span.textContent = str;
        this.options.container.append(span);
        this.textDivs.push(span);
        this.textContentItemsStr.push(str);
      }
      return Promise.resolve();
    }
    cancel() {}
  }

  const getDocument = vi.fn(() => {
    if (fail) {
      fail = false;
      return {
        promise: Promise.reject(new Error('Invalid PDF')),
        destroy: vi.fn(),
      };
    }
    const count = numPages;
    const texts = pageTexts;
    const doc = {
      numPages: count,
      getPage: vi.fn(async (n: number) => page(n, texts)),
      getData: vi.fn(async () => bytes),
    };
    return { promise: Promise.resolve(doc), destroy: vi.fn(async () => {}) };
  });

  const lib = {
    getDocument,
    TextLayer,
    GlobalWorkerOptions: { workerSrc: 'fake' },
  };

  return {
    load: async () => lib,
    getDocument,
    textLayers,
    setPageTexts: (pages) => {
      pageTexts = pages;
    },
    setNumPages: (n) => {
      numPages = n;
    },
    failNext: () => {
      fail = true;
    },
    bytes,
    reset: () => {
      numPages = 3;
      fail = false;
      pageTexts = [];
      textLayers.length = 0;
      getDocument.mockClear();
    },
  };
}

export const fakePdfJs = createFakePdfJs();
export const fakePdfJsModule = { loadPdfJs: () => fakePdfJs.load() };
