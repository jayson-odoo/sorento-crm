'use client';

import * as React from 'react';
import { useReducedMotion, type Transition } from 'motion/react';

/**
 * The one spring every lightbox/menu surface (Dialog, Sheet, Popover,
 * DropdownMenu) opens and closes with (S8-01). Critically damped - `bounce: 0`
 * - because none of these are driven by a flick or a drag; overshoot only
 * belongs on a momentum-carrying gesture (see the apple-design skill,
 * "Behavior over animation" - damping 1.0 is the default, bounce is reserved
 * for a gesture that already carried momentum).
 *
 * `visualDuration` is Apple's "response" half of the damping/response pair,
 * tuned to match `--duration-slow` (300ms, css/config.reui.css) so a JS
 * spring and this app's CSS transitions read at the same pace.
 *
 * A spring re-targets from wherever the value currently sits, so re-opening a
 * surface mid-close continues from its live scale/opacity instead of jumping
 * back to 0 - that is what makes it "interruptible" (S8-01).
 */
export const SURFACE_SPRING: Transition = {
  type: 'spring',
  bounce: 0,
  visualDuration: 0.3,
};

/**
 * Under `prefers-reduced-motion: reduce` the spring collapses to a same-frame
 * opacity change - no scale, no travel, no overshoot (apple-design skill,
 * "Reduced motion & accessibility": a cross-fade, not a slide/spring).
 */
export const REDUCED_MOTION_TRANSITION: Transition = {
  duration: 0.01,
};

/** The transition a surface should animate with, given the user's motion preference. */
export function surfaceTransition(prefersReducedMotion: boolean | null): Transition {
  return prefersReducedMotion ? REDUCED_MOTION_TRANSITION : SURFACE_SPRING;
}

/**
 * initial/animate/exit for a surface materialising in place (S8-01/S8-02):
 * a fade plus a small scale-up. The caller anchors WHERE it grows from via
 * `origin-(--radix-popper-content-transform-origin)` (Radix sets that
 * variable to the trigger side) or a fixed `origin-*` utility for a surface
 * with no Radix popper (the AI assistant panel, S8-05).
 *
 * Reduced motion drops the scale (an overshoot-free zoom still reads as
 * "motion" to someone who asked for none) and keeps only the fade.
 */
export function surfaceVariants(prefersReducedMotion: boolean | null) {
  if (prefersReducedMotion) {
    return { initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 } };
  }
  return {
    initial: { opacity: 0, scale: 0.96 },
    animate: { opacity: 1, scale: 1 },
    exit: { opacity: 0, scale: 0.96 },
  };
}

/**
 * Mirrors a Radix Root's open state into plain React state so a `Content`
 * sibling can read it and gate an `<AnimatePresence>` - Radix's own Presence
 * unmounts on `data-state` + a CSS animation it can detect, which a JS spring
 * is not, so the two open/close paths would otherwise race (see dialog.tsx).
 *
 * Same controlled/uncontrolled contract Radix's own primitives use: pass
 * `open` to run it controlled, omit it to let this own the value.
 */
export function useOpenState(
  propOpen: boolean | undefined,
  defaultOpen: boolean,
  onOpenChange: ((open: boolean) => void) | undefined,
): [boolean, (open: boolean) => void] {
  const [uncontrolledOpen, setUncontrolledOpen] = React.useState(defaultOpen);
  const isControlled = propOpen !== undefined;
  const open = isControlled ? propOpen : uncontrolledOpen;

  const setOpen = React.useCallback(
    (next: boolean) => {
      if (!isControlled) setUncontrolledOpen(next);
      onOpenChange?.(next);
    },
    [isControlled, onOpenChange],
  );

  return [open, setOpen];
}

export { useReducedMotion };
export type { Transition };
