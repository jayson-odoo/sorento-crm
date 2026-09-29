/**
 * The one place pdf.js is imported.
 *
 * Loaded on demand (a dynamic `import()`), so a page that never opens a PDF never downloads
 * the library. The worker is resolved with `new URL(..., import.meta.url)`, which the bundler
 * emits as a static asset under `/_next/static`: same origin, no CDN, and no CSP exception.
 */
export type PdfJs = typeof import('pdfjs-dist');

let loading: Promise<PdfJs> | null = null;

export function loadPdfJs(): Promise<PdfJs> {
  if (!loading) {
    loading = import('pdfjs-dist')
      .then((pdfjs) => {
        if (!pdfjs.GlobalWorkerOptions.workerSrc) {
          pdfjs.GlobalWorkerOptions.workerSrc = new URL(
            'pdfjs-dist/build/pdf.worker.min.mjs',
            import.meta.url,
          ).toString();
        }
        return pdfjs;
      })
      .catch((error) => {
        // A failed chunk load should not poison every later attempt in this tab.
        loading = null;
        throw error;
      });
  }
  return loading;
}
