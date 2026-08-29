'use client';

import * as React from 'react';

/**
 * Tracks whether a scroll container has more content to its right.
 *
 * A strip that scrolls sideways with no visible scrollbar is invisible unless
 * something marks the edge, so both surfaces that scroll horizontally - the tab
 * list and the DataGrid - fade their right edge while there is more to see. The
 * fade has to vanish once the container fits or once the user has reached the
 * end, or it reads as a permanently half-drawn column.
 *
 * Returns `isFading` (the two conditions combined) so a caller does not repeat
 * the rule in a class expression.
 */
export function useHorizontalOverflow<T extends HTMLElement>() {
  const ref = React.useRef<T | null>(null);
  const [state, setState] = React.useState({ isOverflowing: false, isAtEnd: true });

  const measure = React.useCallback(() => {
    const el = ref.current;
    if (!el) return;
    // 1px of slack: fractional layout widths otherwise leave a fade over a
    // container the user has already scrolled to the end of.
    const isOverflowing = el.scrollWidth - el.clientWidth > 1;
    const isAtEnd = !isOverflowing || Math.abs(el.scrollWidth - el.clientWidth - Math.abs(el.scrollLeft)) <= 1;
    setState((prev) => (prev.isOverflowing === isOverflowing && prev.isAtEnd === isAtEnd ? prev : { isOverflowing, isAtEnd }));
  }, []);

  React.useEffect(() => {
    measure();
    const el = ref.current;
    if (!el) return;

    const observer = new ResizeObserver(measure);
    observer.observe(el);
    el.addEventListener('scroll', measure, { passive: true });
    window.addEventListener('resize', measure);

    return () => {
      observer.disconnect();
      el.removeEventListener('scroll', measure);
      window.removeEventListener('resize', measure);
    };
  }, [measure]);

  return {
    ref,
    isOverflowing: state.isOverflowing,
    isAtEnd: state.isAtEnd,
    isFading: state.isOverflowing && !state.isAtEnd,
  };
}
