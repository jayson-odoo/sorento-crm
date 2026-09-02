'use client';

import { useEffect, useState, type CSSProperties } from 'react';
import { useReducedMotion } from '@/lib/motion';

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
 * **The arm carries no guard on purpose, and that is the whole design.**
 * `next.config.mjs` sets `reactStrictMode: true`, so React mounts every effect,
 * cleans it up and mounts it AGAIN before the browser paints. The first version
 * of this hook remembered the armed target in a ref that the cleanup did not
 * reset: pass one set the ref and queued the frames, the synthetic cleanup
 * cancelled them, and pass two saw the ref already equal to the target and did
 * nothing - so the bar sat frozen at `scaleX(1)` for the entire window on both
 * surfaces (measured, `evidence/M3/README.md` M3-01). The effect now does the
 * same work unconditionally every time it runs and publishes the result as
 * STATE, so a replayed mount simply re-arms; `armed.target === targetMs` is a
 * match on the value rendered, not a "have I run yet" flag, so it cannot get
 * out of step with an effect that ran a different number of times.
 *
 * **Reduced motion is branched on HERE, not left to a class.** Both callers
 * carry `motion-reduce:transition-none` on the bar, and it cannot win: this
 * hook writes the transition as an inline style, and an inline declaration
 * beats any class. Under `prefers-reduced-motion: reduce` the hook therefore
 * arms nothing and simply renders `scaleX(startFraction)`, which makes
 * `startFraction` the LIVE fraction rather than a value read once - both
 * callers already re-render every tick to redraw their label, so the bar steps
 * with the label instead of tweening between the two.
 *
 * `transform` runs on the compositor and never triggers layout, unlike the
 * `width` tween this replaces - `components/common/gpu-properties.inventory.test.ts`
 * is the guardrail that keeps a future bar from reverting to it.
 *
 * @param targetMs Absolute `Date.now()`-comparable deadline. `<= 0` parks the
 *   fill at `startFraction` with no transition (nothing to count down to yet).
 * @param startFraction The proportion (0..1) of the bar still to run. Full
 *   motion reads it once, at the moment `targetMs` is (re)armed; reduced motion
 *   renders it on every tick, so a caller must pass the LIVE fraction
 *   (`remaining / window`) rather than a constant, or the bar never moves for
 *   the person who asked for less motion.
 */
export function useDrainingScaleXFill(targetMs: number, startFraction: number): CSSProperties {
  const prefersReducedMotion = useReducedMotion();
  /** The target this fill is currently transitioning to zero for, and over how long. */
  const [armed, setArmed] = useState<{ target: number; remaining: number } | null>(null);

  useEffect(() => {
    if (prefersReducedMotion || targetMs <= 0) return;
    // Read at arm time: two frames from now is within a frame or two of this,
    // and reading it inside the callback would make the duration depend on
    // when the browser got round to the frame.
    const arm = { target: targetMs, remaining: Math.max(0, targetMs - Date.now()) };
    let second = 0;
    const first = requestAnimationFrame(() => {
      second = requestAnimationFrame(() => setArmed(arm));
    });
    return () => {
      cancelAnimationFrame(first);
      // 0 is never a live handle, so this is a no-op when the outer frame has
      // not fired yet - which is exactly the StrictMode replay's first pass.
      cancelAnimationFrame(second);
    };
    // startFraction is read at arm time only (a re-arm happens on a new
    // targetMs, which always carries its own fresh startFraction with it).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targetMs, prefersReducedMotion]);

  // No transition for someone who asked for less motion: the caller's own tick
  // steps this straight to the fraction it just computed.
  if (prefersReducedMotion) return { transform: `scaleX(${startFraction})` };

  // A new target renders the start fraction again on the SAME frame it arrives,
  // with no transition, without waiting for the effect: the armed value belongs
  // to the target it was armed for, and no other.
  if (armed && armed.target === targetMs) {
    return {
      transform: 'scaleX(0)',
      transitionProperty: 'transform',
      transitionDuration: `${armed.remaining}ms`,
      transitionTimingFunction: 'linear',
    };
  }
  return { transform: `scaleX(${startFraction})` };
}
