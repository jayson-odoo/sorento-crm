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

export const clampZoom = (value: number) =>
  Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Math.round(value * 100) / 100));

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
  if (pages.length === 0) return null;
  let index = pages.findIndex((page) => point.y < page.top + page.height);
  if (index < 0) index = pages.length - 1;
  const page = pages[index];
  return {
    index,
    fx: page.width ? (point.x - page.left) / page.width : 0,
    fy: page.height ? (point.y - page.top) / page.height : 0,
  };
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
  return {
    left: Math.max(0, page.left + anchor.fx * page.width - cursor.x),
    top: Math.max(0, page.top + anchor.fy * page.height - cursor.y),
  };
}

const WHEEL_SENSITIVITY = 0.002;
const LINE_HEIGHT_PX = 40;
const PAGE_HEIGHT_PX = 800;
const MAX_WHEEL_FACTOR = 2;

/**
 * The zoom factor for one ctrl+wheel event. A mouse wheel notch (deltaY about 100) is
 * about one toolbar step; a trackpad pinch sends many small deltas, which compound to the
 * same feel. Line and page delta modes are converted to pixels first.
 */
export function wheelZoomFactor(deltaY: number, deltaMode = 0): number {
  const pixels =
    deltaMode === 1
      ? deltaY * LINE_HEIGHT_PX
      : deltaMode === 2
        ? deltaY * PAGE_HEIGHT_PX
        : deltaY;
  const factor = Math.exp(-pixels * WHEEL_SENSITIVITY);
  return Math.min(MAX_WHEEL_FACTOR, Math.max(1 / MAX_WHEEL_FACTOR, factor));
}
