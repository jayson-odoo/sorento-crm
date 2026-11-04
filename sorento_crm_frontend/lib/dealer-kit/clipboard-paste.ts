/**
 * What a Ctrl+V into the tag designer means (DESIGNER-PASTE,
 * `documentation/plans/dealer-kit/PLAN-designer-paste-03nov.md`).
 *
 * The browser's `paste` event carries the SYSTEM clipboard; the editor's own
 * copied layers live in `tag-clipboard.ts`. When the editor copies layers it
 * also writes `TAG_LAYERS_MIME` onto the system clipboard, so a later paste can
 * tell "the layers I copied here" from "a screenshot I copied elsewhere since".
 */

import type { TagLayer } from './tag-template-types';

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
 * The words of the copied text layers: what the editor puts on the system
 * clipboard as `text/plain` beside its marker, so pasting them into a text box
 * elsewhere gives the words. Also what a paste compares against when the
 * marker could not be written (see `classifyPaste`).
 */
export function copiedLayersText(layers: readonly TagLayer[]): string {
  return layers
    .map((layer) => (layer.props.kind === 'text' ? layer.props.text : ''))
    .filter(Boolean)
    .join('\n');
}

/**
 * What a paste means. `copiedText` is `copiedLayersText` of the editor's own
 * clipboard, or null when the editor holds no copied layers.
 *
 * 1. The editor's marker (and layers to go with it): the copied layers.
 * 2. Plain text equal to the copied layers' words: the copied layers too. This
 *    is the fallback for a browser that fired no `copy` event, where the
 *    editor wrote the words with `navigator.clipboard.writeText` instead.
 * 3. An image file: an image paste, unless the clipboard came from a document
 *    (Word, Excel: RTF, or HTML with no picture in it), where Chrome on Windows
 *    adds a picture of the text and the text is what was meant.
 * 4. Non-blank text: a text layer.
 * 5. Otherwise the copied layers, if any.
 */
export function classifyPaste(
  data: PasteData | null,
  copiedText: string | null,
): PasteIntent {
  const hasCopied = copiedText !== null;
  if (!data) return hasCopied ? { kind: 'layers' } : { kind: 'none' };
  const types = Array.from(data.types);
  if (hasCopied && types.includes(TAG_LAYERS_MIME)) return { kind: 'layers' };

  const text = (data.getData('text/plain') ?? '').replace(/\r\n?/g, '\n');
  const blank = !text.trim();
  if (hasCopied && !blank && text.trim() === copiedText.trim())
    return { kind: 'layers' };

  const files = Array.from(data.files ?? []);
  const image = files.find((file) => file.type.startsWith('image/'));
  if (image) {
    const fromDocument =
      types.includes('text/rtf') ||
      (types.includes('text/html') &&
        !/<img\b/i.test(data.getData('text/html') ?? ''));
    if (blank || !fromDocument) return { kind: 'image', file: image };
  }

  if (!blank) return { kind: 'text', text };

  return hasCopied ? { kind: 'layers' } : { kind: 'none' };
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
