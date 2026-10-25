/**
 * Text layers re-measure when a font face finishes loading (PRICETAG-BARCODE-MATCH).
 * Without this, lines broken on the fallback face were printed in the wider
 * brand face and clipped.
 */
import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { useFontsEpoch } from './use-fonts-epoch';

describe('useFontsEpoch', () => {
  afterEach(() => {
    delete (document as unknown as { fonts?: unknown }).fonts;
  });

  it('goes up each time the document finishes loading a font face', () => {
    const fonts = new EventTarget();
    (document as unknown as { fonts: EventTarget }).fonts = fonts;

    const { result } = renderHook(() => useFontsEpoch());
    expect(result.current).toBe(0);

    act(() => {
      fonts.dispatchEvent(new Event('loadingdone'));
    });
    expect(result.current).toBe(1);

    act(() => {
      fonts.dispatchEvent(new Event('loadingdone'));
    });
    expect(result.current).toBe(2);
  });

  it('stops listening once unmounted', () => {
    const fonts = new EventTarget();
    (document as unknown as { fonts: EventTarget }).fonts = fonts;

    const { result, unmount } = renderHook(() => useFontsEpoch());
    unmount();
    act(() => {
      fonts.dispatchEvent(new Event('loadingdone'));
    });
    expect(result.current).toBe(0);
  });
});
