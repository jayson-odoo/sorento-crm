'use client';

/**
 * Load an image for Konva.
 *
 * Konva needs a real HTMLImageElement rather than a URL, and re-rendering with
 * a half-loaded one paints nothing, so the element only reaches the stage once
 * it has decoded.
 *
 * A file of its own, not a member of `KonvaTagLayer.tsx` (S8): `TagCanvasEditor.tsx`'s
 * crop mode needs the SAME loaded image (to draw the dimmed "whole source"
 * behind the crop window) without pulling in the rest of that file's exports -
 * several existing tests mock `./KonvaTagLayer` down to just its one named
 * export, and a second import from it would crash every one of them the
 * moment this hook ran.
 *
 * **No `crossOrigin`.** It used to be `anonymous`, for a reason that does not
 * hold: a signed URL needs no CORS, and `anonymous` makes the browser DISCARD
 * an image whose response carries no `Access-Control-Allow-Origin`. The R2
 * bucket serving library assets sends none, so every badge, icon and diagram on
 * a tag failed to decode and sat on the placeholder text below forever - which
 * is exactly what the eight seeded templates showed, all 28 pieces of artwork,
 * on a canvas that was otherwise correct.
 *
 * What `anonymous` would buy is an UNTAINTED canvas, and nothing here wants
 * one: the tag PDF is rendered by headless Chromium against the print page, not
 * by `stage.toDataURL()`, and there is no `toDataURL` anywhere under
 * `dealer-kit/`. Bring it back only alongside a client-side canvas export - and
 * with a CORS rule on the bucket, or the export will draw blanks instead.
 */

import { useEffect, useState } from 'react';

export function useHtmlImage(url: string | null | undefined): HTMLImageElement | null {
  const [image, setImage] = useState<HTMLImageElement | null>(null);

  useEffect(() => {
    if (!url) {
      setImage(null);
      return;
    }
    let live = true;
    const element = new window.Image();
    element.src = url;
    element.onload = () => {
      if (live) setImage(element);
    };
    element.onerror = () => {
      if (live) setImage(null);
    };
    return () => {
      live = false;
    };
  }, [url]);

  return image;
}
