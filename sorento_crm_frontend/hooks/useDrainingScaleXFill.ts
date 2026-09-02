'use client';

import { useEffect, useRef, useState, type CSSProperties } from 'react';

/**
 * The ONE shared mechanism every fill bar counting down against a server
 * `commit_at`/absolute deadline drains through (M3-01, M3-02,
 * `ui-motion-round2`): DeferredActionButton's countdown, TakeoverCountdown.
 *
 * Arms a `transform: scaleX()` CSS transition, ONCE per distinct `targetMs`,
 * from the CURRENT proportion left (so a late mount - e.g. a tab-switch
 * remount partway through the window - paints a short bar immediately rather
 * than animating down from full) to `scaleX(0)` by `targetMs`. A double rAF
 * is what makes the transition run at all: the first frame has to land at
 * the starting scale with no transition property set, or there is nothing
 * for the second frame's flip to `scaleX(0)` to animate FROM.
 *
 * `transform` runs on the compositor and never triggers layout, unlike the
 * `width` tween this replaces - `components/common/gpu-properties.inventory.test.ts`
 * is the guardrail that keeps a future bar from reverting to it.
 *
 * @param targetMs Absolute `Date.now()`-comparable deadline. `<= 0` parks the
 *   fill at `startFraction` with no transition (nothing to count down to yet).
 * @param startFraction The proportion (0..1) the bar should show as already
 *   elapsed at the moment `targetMs` is (re)armed - `1` for a countdown that
 *   always starts fresh and full, the live remaining fraction for one that
 *   can mount partway through its window.
 */
export function useDrainingScaleXFill(targetMs: number, startFraction: number): CSSProperties {
  const [style, setStyle] = useState<CSSProperties>(() => ({
    transform: `scaleX(${startFraction})`,
  }));
  const armedTargetRef = useRef<number | null>(null);

  useEffect(() => {
    if (targetMs <= 0 || armedTargetRef.current === targetMs) return;
    armedTargetRef.current = targetMs;
    setStyle({ transform: `scaleX(${startFraction})` });
    const remaining = Math.max(0, targetMs - Date.now());
    let raf2 = 0;
    const raf1 = requestAnimationFrame(() => {
      raf2 = requestAnimationFrame(() => {
        setStyle({
          transform: 'scaleX(0)',
          transitionProperty: 'transform',
          transitionDuration: `${remaining}ms`,
          transitionTimingFunction: 'linear',
        });
      });
    });
    return () => {
      cancelAnimationFrame(raf1);
      if (raf2) cancelAnimationFrame(raf2);
    };
    // startFraction is read at arm time only (a re-arm happens on a new
    // targetMs, which always carries its own fresh startFraction with it).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targetMs]);

  return style;
}
