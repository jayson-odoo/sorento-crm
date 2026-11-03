/**
 * What a Ctrl+V into the tag designer means (DESIGNER-PASTE,
 * `documentation/plans/dealer-kit/PLAN-designer-paste-03nov.md`).
 *
 * The browser's `paste` event carries the SYSTEM clipboard; the editor's own
 * copied layers live in `tag-clipboard.ts`. When the editor copies layers it
 * also writes `TAG_LAYERS_MIME` onto the system clipboard, so a later paste can
 * tell "the layers I copied here" from "a screenshot I copied elsewhere since".
 */

/** Marker the editor writes on its own copy/cut, read back on paste. */
export const TAG_LAYERS_MIME = 'application/x-sorento-tag-layers';

/** Same cap as the Image tool's picker (`AssetPickerDialog`, `maxSizeMb={20}`). */
export const PASTE_IMAGE_MAX_BYTES = 20 * 1024 * 1024;

/** Same types as the Image tool's picker accepts (.png .jpg .jpeg .webp .svg). */
const PASTE_IMAGE_TYPES = new Set([
  'image/png',
  'image/jpeg',
  'image/webp',
  'image/svg+xml',
]);

/** CSS pixel size: 96 px to the inch. */
const MM_PER_PX = 25.4 / 96;

/** The parts of `DataTransfer` this reads, so tests can hand in a plain object. */
export interface PasteData {
  types: readonly string[];
  getData(type: string): string;
  files?: ArrayLike<File> | null;
}

export type PasteIntent =
  | { kind: 'layers' }
  | { kind: 'image'; file: File }
  | { kind: 'text'; text: string }
  | { kind: 'none' };

/**
 * Editor marker first, then an image file, then non-blank text, then the
 * editor's own copied layers (`hasCopiedLayers`) as the fallback.
 */
export function classifyPaste(
  data: PasteData | null,
  hasCopiedLayers: boolean,
): PasteIntent {
  if (!data) return hasCopiedLayers ? { kind: 'layers' } : { kind: 'none' };
  if (Array.from(data.types).includes(TAG_LAYERS_MIME))
    return { kind: 'layers' };

  const files = Array.from(data.files ?? []);
  const image = files.find((file) => file.type.startsWith('image/'));
  if (image) return { kind: 'image', file: image };

  const text = (data.getData('text/plain') ?? '').replace(/\r\n?/g, '\n');
  if (text.trim()) return { kind: 'text', text };

  return hasCopiedLayers ? { kind: 'layers' } : { kind: 'none' };
}

/** Why a pasted image cannot be uploaded, or null when it can. */
export function pastedImageProblem(file: File): string | null {
  if (!PASTE_IMAGE_TYPES.has(file.type)) {
    return 'Only PNG, JPG, WebP or SVG images can be pasted';
  }
  if (file.size > PASTE_IMAGE_MAX_BYTES) {
    return 'The pasted image is larger than 20 MB';
  }
  return null;
}

/**
 * Where a pasted picture lands: its natural size at 96 dpi, scaled down (never
 * up) to fit inside the canvas with the aspect kept, centred.
 */
export function fitPastedImage(
  natural: { width: number; height: number } | null,
  canvas: { width_mm: number; height_mm: number },
): { x_mm: number; y_mm: number; width_mm: number; height_mm: number } {
  let width: number;
  let height: number;
  if (natural && natural.width > 0 && natural.height > 0) {
    width = natural.width * MM_PER_PX;
    height = natural.height * MM_PER_PX;
  } else {
    width = 40;
    height = 30;
  }
  const scale = Math.min(1, canvas.width_mm / width, canvas.height_mm / height);
  width *= scale;
  height *= scale;
  return {
    x_mm: (canvas.width_mm - width) / 2,
    y_mm: (canvas.height_mm - height) / 2,
    width_mm: width,
    height_mm: height,
  };
}

/** The image's pixel size, or null when the browser cannot decode it. */
export function readImageSize(
  file: File,
): Promise<{ width: number; height: number } | null> {
  return new Promise((resolve) => {
    if (typeof URL.createObjectURL !== 'function') {
      resolve(null);
      return;
    }
    const url = URL.createObjectURL(file);
    const img = new Image();
    const done = (size: { width: number; height: number } | null) => {
      URL.revokeObjectURL(url);
      resolve(size);
    };
    img.onload = () =>
      done({ width: img.naturalWidth, height: img.naturalHeight });
    img.onerror = () => done(null);
    img.src = url;
  });
}
