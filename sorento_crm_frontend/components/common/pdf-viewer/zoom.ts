/**
 * Zoom math for `PdfViewer`, kept pure so it can be tested without layout.
 *
 * Zooming around a point: before the zoom, the point under the cursor is recorded as a
 * fraction of the page it sits on. Fractions do not change with scale, so after the pages
 * re-render at the new size the same fraction of the same page is put back under the cursor.
 */
export const ZOOM_MIN = 0.25;
export const ZOOM_MAX = 5;
export const ZOOM_STEP = 1.25;

export const clampZoom = (value: number) => {
  throw new Error('not implemented');
};

/** A page's box in the scroller's content coordinates (its offsetLeft/Top/Width/Height). */
export interface PageBox {
  left: number;
  top: number;
  width: number;
  height: number;
}

/** A point in the document that survives a change of scale. */
export interface ZoomAnchor {
  /** Index of the page the point belongs to. */
  index: number;
  /** Where on that page, as a fraction of its width and height. */
  fx: number;
  fy: number;
}

export interface Point {
  x: number;
  y: number;
}

/**
 * Records the document point at `point` (content coordinates: scroll offset plus the
 * cursor's position inside the scroller). A point in the gap between pages, or in the
 * margin, belongs to the nearest page below it (or the last page), with a fraction outside
 * 0..1, so it still maps back exactly.
 */
export function captureAnchor(
  pages: PageBox[],
  point: Point,
): ZoomAnchor | null {
  throw new Error('not implemented');
}

/**
 * The scroll offset that puts `anchor`, on a page now laid out at `page`, back under
 * `cursor` (the cursor's position inside the scroller's visible box).
 */
export function anchoredScroll(
  page: PageBox,
  anchor: ZoomAnchor,
  cursor: Point,
): { left: number; top: number } {
  throw new Error('not implemented');
}

/**
 * The zoom factor for one ctrl+wheel event. A mouse wheel notch (deltaY about 100) is
 * about one toolbar step; a trackpad pinch sends many small deltas, which compound to the
 * same feel. Line and page delta modes are converted to pixels first.
 */
export function wheelZoomFactor(deltaY: number, deltaMode = 0): number {
  throw new Error('not implemented');
}
