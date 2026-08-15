import type { CSSProperties } from 'react';

import type { SectionStyle } from './types';

/**
 * The surface a section is painted on, artwork included.
 *
 * ONE implementation, shared by every surface that draws a section: the public
 * catalogue, the printed PDF, the builder canvas and its paper preview. It sits
 * here, beside `gridMetrics`, for the reason that module exists - the builder
 * and the published renderer lay the same blocks out with different engines,
 * and while each kept its own copy of a shared number they drifted, so a page
 * that looked right in the builder overlapped once published. A background is
 * the same kind of fact. A second implementation is how the editor and the
 * published page start disagreeing, which is precisely the defect this feature
 * was built to avoid: the designer approves what they can see.
 *
 * The artwork is a BACKGROUND and the heading stays a text block on top of it.
 * Keeping the heading inside the bitmap, where the designer originally put it,
 * would look identical in a screenshot and would be a heading nobody can
 * correct, search for or translate - and the flyer extractor is known to misread
 * them (one page of the real flyer reads "Transforming Your" where the paper
 * says "BATHTUB COLLECTION").
 *
 * An asset with no entry in `assets` renders as no artwork at all. The server
 * signs strictly and omits anything it could not sign, because the section has a
 * designed state for "no picture" and none whatsoever for "a picture the CDN
 * answers 403 to".
 */
export function sectionSurface(
  style: SectionStyle | undefined,
  assets: Record<string, string> | undefined,
): CSSProperties | undefined {
  const base = style?.background ? { background: style.background } : undefined;

  const assetId = style?.backgroundAssetId;
  const url = assetId ? assets?.[assetId] : undefined;
  if (!url) return base;

  const cover = style?.backgroundFit === 'cover';
  return {
    // The plain background stays underneath, and stays FIRST: `background` is a
    // shorthand, so declaring it after the image would reset the image away.
    ...base,
    backgroundImage: `url(${JSON.stringify(url)})`,
    // `100%` is the one-value form of "full width, height from the aspect
    // ratio". Written as one value rather than `100% auto` because that is what
    // every CSSOM round trip gives back anyway, and two spellings of one
    // declaration is one more than a test can assert.
    backgroundSize: cover ? 'cover' : '100%',
    backgroundRepeat: 'no-repeat',
    backgroundPosition: cover ? 'center center' : 'center top',
  } as CSSProperties;
}

/**
 * True when this section actually paints artwork.
 *
 * Not the same question as "does it bind an asset": an asset the server could
 * not sign is absent from the map, and the section is then a plain one. The
 * builder needs the resolved answer, because that is what decides whether its
 * block frames sit on a picture or on the page background.
 */
export function hasArtwork(
  style: SectionStyle | undefined,
  assets: Record<string, string> | undefined,
): boolean {
  const assetId = style?.backgroundAssetId;
  return Boolean(assetId && assets?.[assetId]);
}
