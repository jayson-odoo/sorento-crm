/**
 * Pure geometry for the box overlay drawn on a PDF page. A box is stored as FRACTIONS (0..1) of the
 * page as displayed, origin top-left, so it survives any zoom. Pixel inputs are in the page's own
 * on-screen size.
 */
export interface PageBox {
  page: number;
  x: number;
  y: number;
  w: number;
  h: number;
  product_id: string | null;
  /** A box merged from several products on one table row: every product that fed it. */
  product_ids?: string[];
}

export type Corner = 'nw' | 'ne' | 'sw' | 'se';

export const MIN_BOX = 0.005;

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
const pct = (v: number) => `${Number((v * 100).toFixed(4))}%`;

export function boxToStyle(box: Pick<PageBox, 'x' | 'y' | 'w' | 'h'>) {
  return { left: pct(box.x), top: pct(box.y), width: pct(box.w), height: pct(box.h) };
}

export function rectFromDrag(
  a: { x: number; y: number },
  b: { x: number; y: number },
  page: { width: number; height: number },
) {
  const fx = (v: number) => clamp(v / page.width, 0, 1);
  const fy = (v: number) => clamp(v / page.height, 0, 1);
  const x0 = Math.min(fx(a.x), fx(b.x));
  const x1 = Math.max(fx(a.x), fx(b.x));
  const y0 = Math.min(fy(a.y), fy(b.y));
  const y1 = Math.max(fy(a.y), fy(b.y));
  return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
}

export function moveBox<T extends PageBox>(box: T, dx: number, dy: number): T {
  return {
    ...box,
    x: clamp(box.x + dx, 0, 1 - box.w),
    y: clamp(box.y + dy, 0, 1 - box.h),
  };
}

export function resizeBox<T extends PageBox>(box: T, corner: Corner, dx: number, dy: number): T {
  let left = box.x;
  let top = box.y;
  let right = box.x + box.w;
  let bottom = box.y + box.h;
  if (corner === 'nw' || corner === 'sw') left = clamp(left + dx, 0, right - MIN_BOX);
  else right = clamp(right + dx, left + MIN_BOX, 1);
  if (corner === 'nw' || corner === 'ne') top = clamp(top + dy, 0, bottom - MIN_BOX);
  else bottom = clamp(bottom + dy, top + MIN_BOX, 1);
  return { ...box, x: left, y: top, w: right - left, h: bottom - top };
}

/**
 * The boxes to save as per-product defaults: a box merged from several products becomes one box
 * per product (each product keeps its own default on that row); any other box goes to its own
 * product, else to `fallbackProductId` (the product chosen while drawing).
 */
export function expandBoxesForDefault(boxes: PageBox[], fallbackProductId: string | null): PageBox[] {
  return boxes.flatMap((box) => {
    const { product_ids: ids, ...rest } = box;
    const targets = ids && ids.length > 1 ? ids : [box.product_id ?? fallbackProductId];
    return targets.map((product_id) => ({ ...rest, product_id }));
  });
}
