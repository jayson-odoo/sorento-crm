/**
 * Brand fonts, loaded before anything draws with them.
 *
 * A tag can be set in the brand's own typeface (D29): the font is a file in the
 * Dealer Kit library, and both surfaces that draw a tag have to have it before
 * they draw. They fail in different but equally quiet ways without this - Konva
 * measures text against whatever font is loaded AT THAT MOMENT, so a canvas
 * rendered before the face arrives lays out in the fallback and never
 * re-measures; the print page reports ready and Chromium prints the fallback.
 *
 * So loading is explicit and awaited, and the caller decides what to do while
 * it happens.
 */

export interface TagFont {
  /** What a person picked in the inspector. Also the CSS family name. */
  name: string;
  family: string;
  /** Signed URL for the font file. */
  url: string;
}

const loaded = new Set<string>();

/**
 * Register every font with the document and wait for them.
 *
 * Idempotent per family+url: the editor calls this on every load of the font
 * list, and re-adding a `FontFace` would grow `document.fonts` without bound.
 * Resolves even when a face fails - a tag set in the fallback is worse than one
 * in the brand face, and far better than an editor that never renders.
 */
export async function ensureFontsLoaded(fonts: TagFont[]): Promise<void> {
  if (typeof document === 'undefined' || typeof FontFace === 'undefined') return;

  const pending: Promise<unknown>[] = [];

  for (const font of fonts) {
    const key = `${font.family}|${font.url}`;
    if (!font.url || !font.family || loaded.has(key)) continue;
    loaded.add(key);

    try {
      const face = new FontFace(font.family, `url(${JSON.stringify(font.url)})`);
      pending.push(
        face
          .load()
          .then((result) => {
            document.fonts.add(result);
          })
          .catch(() => {
            // A font that will not load leaves the layer in its fallback.
            loaded.delete(key);
          }),
      );
    } catch {
      loaded.delete(key);
    }
  }

  await Promise.all(pending);
  try {
    await document.fonts.ready;
  } catch {
    // `document.fonts.ready` rejecting is not a reason to hold up a render.
  }
}

/** Forget what has been loaded. For tests only. */
export function _resetLoadedFonts(): void {
  loaded.clear();
}
