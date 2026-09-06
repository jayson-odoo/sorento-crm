'use client';

import * as React from 'react';

/**
 * Tracks whether a scroll container has more content to either side.
 *
 * A strip that scrolls sideways with no visible scrollbar is invisible unless
 * something marks the edge, so every surface that scrolls horizontally - the
 * tab list and the DataGrid - fades an edge while there is more to see past
 * it. The fade has to vanish once the container fits or once the user has
 * reached that edge, or it reads as a permanently half-drawn column.
 *
 * `isFadingEnd` is the original single-edge signal (DataGrid only ever scrolls
 * away from its start, never back past it visually); `isFading` stays as its
 * alias so that caller, and anything else already reading it, keeps working
 * unchanged. `isFadingStart` is the mirror of it, for a strip - like the tabs
 * list - that can be scrolled from either direction.
 */
export function useHorizontalOverflow<T extends HTMLElement>() {
  const ref = React.useRef<T | null>(null);
  const [state, setState] = React.useState({ isOverflowing: false, isAtStart: true, isAtEnd: true });

  const measure = React.useCallback(() => {
    const el = ref.current;
    if (!el) return;
    // 1px of slack: fractional layout widths otherwise leave a fade over a
    // container the user has already scrolled to the edge of.
    const isOverflowing = el.scrollWidth - el.clientWidth > 1;
    // `Math.abs` on `scrollLeft` because RTL browsers report it negative.
    const isAtStart = !isOverflowing || Math.abs(el.scrollLeft) <= 1;
    const isAtEnd = !isOverflowing || Math.abs(el.scrollWidth - el.clientWidth - Math.abs(el.scrollLeft)) <= 1;
    setState((prev) =>
      prev.isOverflowing === isOverflowing && prev.isAtStart === isAtStart && prev.isAtEnd === isAtEnd
        ? prev
        : { isOverflowing, isAtStart, isAtEnd },
    );
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

  const isFadingEnd = state.isOverflowing && !state.isAtEnd;

  return {
    ref,
    isOverflowing: state.isOverflowing,
    isAtStart: state.isAtStart,
    isAtEnd: state.isAtEnd,
    isFadingStart: state.isOverflowing && !state.isAtStart,
    isFadingEnd,
    isFading: isFadingEnd,
  };
}
