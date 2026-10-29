'use client';

/**
 * A number that goes up every time the document finishes loading a font face.
 *
 * Text layers break their lines by measuring on a canvas (`textLayerLines`),
 * and a measure taken before a brand face arrives measured the fallback. The
 * canvas and the request preview both load faces after their first draw, so
 * each text layer re-measures when this changes.
 */

import { useEffect, useState } from 'react';

export function useFontsEpoch(): number {
  const [epoch, setEpoch] = useState(0);

  useEffect(() => {
    const fonts = typeof document === 'undefined' ? undefined : document.fonts;
    if (!fonts?.addEventListener) return;
    const bump = () => setEpoch((value) => value + 1);
    fonts.addEventListener('loadingdone', bump);
    return () => fonts.removeEventListener('loadingdone', bump);
  }, []);

  return epoch;
}
