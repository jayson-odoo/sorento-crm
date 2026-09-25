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
  const bytes = new Uint8Array([37, 80, 68, 70]);
  const textLayers: { container: HTMLElement }[] = [];

  const page = (pageNumber: number) => ({
    pageNumber,
    userUnit: 1,
    getViewport: ({ scale }: { scale: number }) => ({
      width: 600 * scale,
      height: 800 * scale,
      scale,
    }),
    render: vi.fn(() => ({ promise: Promise.resolve(), cancel: vi.fn() })),
    streamTextContent: vi.fn(() => ({})),
  });

  class TextLayer {
    constructor(options: { container: HTMLElement }) {
      textLayers.push(options);
    }
    render() {
      return Promise.resolve();
    }
    cancel() {}
  }

  const getDocument = vi.fn(() => {
    if (fail) {
      fail = false;
      return { promise: Promise.reject(new Error('Invalid PDF')), destroy: vi.fn() };
    }
    const count = numPages;
    const doc = {
      numPages: count,
      getPage: vi.fn(async (n: number) => page(n)),
      getData: vi.fn(async () => bytes),
    };
    return { promise: Promise.resolve(doc), destroy: vi.fn(async () => {}) };
  });

  const lib = { getDocument, TextLayer, GlobalWorkerOptions: { workerSrc: 'fake' } };

  return {
    load: async () => lib,
    getDocument,
    textLayers,
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
      textLayers.length = 0;
      getDocument.mockClear();
    },
  };
}

export const fakePdfJs = createFakePdfJs();
export const fakePdfJsModule = { loadPdfJs: () => fakePdfJs.load() };
