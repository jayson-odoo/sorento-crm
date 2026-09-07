/**
 * Image crop rect: normalised [0, 1] against the SOURCE image, applied
 * BEFORE `fit` (S8).
 *
 * `fit` then places whatever this rect selects into the layer's own box,
 * exactly as it placed the whole image before this round - `maskShape`
 * stays on the box either way, untouched by any of this. Absent `cropRect`
 * means the whole image, so a template saved before S8 renders exactly as
 * it did (AC-S8-6): every function here treats `undefined`/`null` as
 * `FULL_CROP` rather than requiring a caller to branch on it first.
 */

export interface CropRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** The whole image - what an absent `cropRect` means. */
export const FULL_CROP: CropRect = { x: 0, y: 0, width: 1, height: 1 };

/** Smallest a crop window is allowed to shrink to, either axis. */
const MIN_CROP_FRACTION = 0.02;

/**
 * Clamp to a window that stays inside [0, 1] on both axes and never
 * collapses to zero (a handle dragged onto its opposite edge, or a corrupt
 * saved value, would otherwise divide by zero everywhere below).
 */
function clampCropRect(rect: CropRect): CropRect {
  const width = Math.min(Math.max(rect.width, MIN_CROP_FRACTION), 1);
  const height = Math.min(Math.max(rect.height, MIN_CROP_FRACTION), 1);
  const x = Math.min(Math.max(rect.x, 0), 1 - width);
  const y = Math.min(Math.max(rect.y, 0), 1 - height);
  return { x, y, width, height };
}

/** `cropRect`, resolved: absent reads as the whole image, and the result is
 * always safe to divide by (clamped, never zero-sized). */
export function resolvedCropRect(cropRect: CropRect | null | undefined): CropRect {
  return clampCropRect(cropRect ?? FULL_CROP);
}

/** Whether a crop actually selects less than the whole image. */
export function isCropped(cropRect: CropRect | null | undefined): boolean {
  if (!cropRect) return false;
  const rect = resolvedCropRect(cropRect);
  return rect.x > 0 || rect.y > 0 || rect.width < 1 || rect.height < 1;
}

/**
 * The crop window's own 8 anchors, one per Transformer anchor name, as
 * fractions of the WINDOW's own width/height (S8, AC-S8-2): `fx`/`fy` of 0
 * is the left/top edge, 1 the right/bottom edge, 0.5 the untouched middle.
 */
export const CROP_HANDLE_ANCHORS: { name: string; fx: number; fy: number }[] = [
  { name: 'top-left', fx: 0, fy: 0 },
  { name: 'top-center', fx: 0.5, fy: 0 },
  { name: 'top-right', fx: 1, fy: 0 },
  { name: 'middle-left', fx: 0, fy: 0.5 },
  { name: 'middle-right', fx: 1, fy: 0.5 },
  { name: 'bottom-left', fx: 0, fy: 1 },
  { name: 'bottom-center', fx: 0.5, fy: 1 },
  { name: 'bottom-right', fx: 1, fy: 1 },
];

/**
 * Drag one crop-window handle (S8): `normDx`/`normDy` are the pointer's own
 * delta from where the drag started, normalised against the FITTED source
 * frame's own width/height (the same units `base` is in). An edge fraction
 * of 0 moves that edge WITH the drag and shrinks the opposite dimension by
 * the same amount; 1 grows it; 0.5 (the untouched middle of that axis) is
 * left alone - one rule covers all 8 anchors without special-casing any of
 * them. `resolvedCropRect` at the end is what keeps every handle clamped to
 * the source bounds (AC-S8-2): a drag past the far edge or past the
 * opposite handle just stops there instead of inverting the rect.
 */
export function cropRectFromDrag(
  base: CropRect,
  anchor: { fx: number; fy: number },
  normDx: number,
  normDy: number,
): CropRect {
  let { x, y, width, height } = base;
  if (anchor.fx === 0) {
    x = base.x + normDx;
    width = base.width - normDx;
  } else if (anchor.fx === 1) {
    width = base.width + normDx;
  }
  if (anchor.fy === 0) {
    y = base.y + normDy;
    height = base.height - normDy;
  } else if (anchor.fy === 1) {
    height = base.height + normDy;
  }
  return resolvedCropRect({ x, y, width, height });
}

/**
 * Pan the crop window (dragging INSIDE it, not on a handle) - width and
 * height are untouched, `resolvedCropRect` keeps the window from panning
 * past the source bounds on either axis (AC-S8-2).
 */
export function panCropRect(base: CropRect, normDx: number, normDy: number): CropRect {
  return resolvedCropRect({ ...base, x: base.x + normDx, y: base.y + normDy });
}

/**
 * The normalised rect in SOURCE PIXELS, for Konva's own `crop={{x, y,
 * width, height}}` prop on an `Image` node (`KonvaTagLayer.tsx`).
 */
export function cropPixels(
  cropRect: CropRect | null | undefined,
  image: { width: number; height: number },
): { x: number; y: number; width: number; height: number } {
  const rect = resolvedCropRect(cropRect);
  return {
    x: rect.x * image.width,
    y: rect.y * image.height,
    width: rect.width * image.width,
    height: rect.height * image.height,
  };
}

/**
 * Where the CROPPED region draws inside the layer's own box, per `fit`
 * (S8) - the SAME maths `KonvaTagLayer.tsx`'s `ImageContent` uses to place
 * its `KonvaImage`. Exported so the canvas crop-mode overlay
 * (`TagCanvasEditor.tsx`) can derive its own placement from this ONE
 * function too, rather than a second copy that can drift from it (r6 S8
 * review, #723): the reported bug was exactly that drift - the overlay
 * fit the WHOLE source always CONTAIN while the real layer fits the
 * CROPPED region per its own `fit`, so the two disagreed on scale and
 * centring and the picture looked doubled.
 */
export function fittedCropDraw(
  cropRect: CropRect | null | undefined,
  natural: { width: number; height: number },
  fit: 'cover' | 'contain' | 'stretch',
  w: number,
  h: number,
): { x: number; y: number; width: number; height: number } {
  const crop = cropPixels(cropRect, natural);
  let drawW: number;
  let drawH: number;
  if (fit === 'stretch' || crop.width <= 0 || crop.height <= 0) {
    drawW = w;
    drawH = h;
  } else {
    const ratio = crop.width / crop.height;
    const boxRatio = w / h;
    const wide = fit === 'contain' ? ratio > boxRatio : ratio < boxRatio;
    drawW = wide ? w : h * ratio;
    drawH = wide ? w / ratio : h;
  }
  return { x: (w - drawW) / 2, y: (h - drawH) / 2, width: drawW, height: drawH };
}

/**
 * The crop-mode overlay's own layout (S8, r6 S8 review, #723): `window` is
 * the crop selection's on-screen rect - `fittedCropDraw` above, so it is
 * EXACTLY where the real layer will draw the cropped region once this
 * commits. `source` is the WHOLE source image at that SAME scale, offset so
 * the sub-rectangle `cropRect` selects lands exactly under `window` - draw
 * the source ONCE at `source` (dimmed), then the SAME image again at the
 * SAME `source` transform (opaque, clipped to `window`) and the two can
 * never disagree, because they share one transform instead of two
 * independently-derived ones.
 */
export function cropOverlayLayout(
  cropRect: CropRect | null | undefined,
  natural: { width: number; height: number },
  fit: 'cover' | 'contain' | 'stretch',
  w: number,
  h: number,
): {
  window: { x: number; y: number; width: number; height: number };
  source: { x: number; y: number; width: number; height: number };
} {
  const window = fittedCropDraw(cropRect, natural, fit, w, h);
  const crop = cropPixels(cropRect, natural);
  const scaleX = crop.width > 0 ? window.width / crop.width : 1;
  const scaleY = crop.height > 0 ? window.height / crop.height : 1;
  return {
    window,
    source: {
      x: window.x - crop.x * scaleX,
      y: window.y - crop.y * scaleY,
      width: natural.width * scaleX,
      height: natural.height * scaleY,
    },
  };
}

/**
 * The print path's crop-window layout (S8): a wrapper carrying the
 * CROPPED region's own aspect ratio (which only equals the crop fraction's
 * own W:H ratio when the source happens to be square - `natural` is what
 * corrects for that), and the real `<img>` zoomed and offset inside it so
 * only that region ever shows.
 *
 * `TagSheetRenderer.tsx` centres this wrapper into the layer's box per
 * `fit` with `min`/`max`-width percentages plus `aspectRatio` - the
 * `object-fit: cover`/`contain` result for an ordinary `<img>`, reproduced
 * on a plain `<div>` because CSS `object-fit` has no "and only this
 * sub-rectangle" mode to crop with directly.
 */
export function cropWindowStyle(
  cropRect: CropRect | null | undefined,
  natural: { width: number; height: number },
): {
  aspectRatio: string;
  img: { width: string; height: string; left: string; top: string };
} {
  const rect = resolvedCropRect(cropRect);
  const cropWidthPx = rect.width * natural.width;
  const cropHeightPx = rect.height * natural.height;
  return {
    aspectRatio: `${cropWidthPx} / ${cropHeightPx}`,
    img: {
      width: `${100 / rect.width}%`,
      height: `${100 / rect.height}%`,
      left: `${-(rect.x / rect.width) * 100}%`,
      top: `${-(rect.y / rect.height) * 100}%`,
    },
  };
}
