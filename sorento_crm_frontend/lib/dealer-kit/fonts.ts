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
 * The two faces the seeded starter templates are set in.
 *
 * `Sorento Pricetag Template.pdf` is set in Century Gothic and Myriad Pro,
 * which are licensed and cannot ship here; marketing uploads them as
 * `Asset.kind='font'` and the templates pick them up by family NAME, so nothing
 * about a template has to change when they do. Until then the seed names free
 * stand-ins of the same class - Bebas Neue for codes and prices, Jost for the
 * wordmark and body - and something has to actually load them, or Konva
 * measures every seeded tag against a system sans and the layout the tag was
 * transcribed at is not the layout it draws.
 *
 * A stylesheet link rather than `next/font`, because both surfaces address a
 * font by its REAL family name: `next/font` mangles the family into a hashed
 * one, which a layer's `fontFamily: 'Bebas Neue'` would never match.
 */
export const TAG_FONT_STYLESHEET =
  'https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Jost:wght@400;500;600;700&display=swap';

/** The families `TAG_FONT_STYLESHEET` provides, for a readiness check. */
export const SEED_FONT_FAMILIES = ['Bebas Neue', 'Jost'] as const;

/**
 * Wait for the seeded templates' stand-in faces, best effort.
 *
 * Separate from `ensureFontsLoaded` because these arrive through a stylesheet
 * the document already carries rather than as `FontFace` objects this code
 * constructs. Resolving either way is deliberate: an environment with no route
 * to Google draws the tags in a fallback face, which is worse-looking and still
 * completely usable, and is not a reason for an editor never to open or a PDF
 * job never to finish.
 */
export async function ensureSeedFontsLoaded(): Promise<void> {
  if (typeof document === 'undefined' || !document.fonts) return;

  const LINK_ID = 'dk-tag-seed-fonts';
  if (!document.getElementById(LINK_ID)) {
    const link = document.createElement('link');
    link.id = LINK_ID;
    link.rel = 'stylesheet';
    link.href = TAG_FONT_STYLESHEET;
    document.head.appendChild(link);
  }

  try {
    await Promise.all(
      SEED_FONT_FAMILIES.map((family) => document.fonts.load(`16px "${family}"`)),
    );
  } catch {
    // See the docstring: a missing stand-in face is a styling loss, not a stop.
  }
}

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
