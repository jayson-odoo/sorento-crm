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
 * The menu/popper family (Popover, DropdownMenu and the rest of the menu
 * primitives - M2-03) opens on a shorter response than a lightbox: a menu is
 * a quick lookup next to the trigger, not a surface that takes over the
 * screen, so `visualDuration` matches `--duration-base` (200ms) instead of
 * `--duration-slow`.
 */
export const MENU_SPRING: Transition = {
  type: 'spring',
  bounce: 0,
  visualDuration: 0.2,
};

/**
 * The exit half of a lightbox close (M2-03/M2-04). Every surface in this
 * file opens on its own response (0.3s for a lightbox, 0.2s for a menu) but
 * closes on the same 0.2s - a close only has to get out of the way, not
 * announce itself, so there is no reason to hold the lightbox's slower
 * in-transition on the way out.
 */
export const SURFACE_SPRING_EXIT: Transition = {
  type: 'spring',
  bounce: 0,
  visualDuration: 0.2,
};

/**
 * Under `prefers-reduced-motion: reduce` the spring collapses to a same-frame
 * opacity change - no scale, no travel, no overshoot (apple-design skill,
 * "Reduced motion & accessibility": a cross-fade, not a slide/spring).
 */
export const REDUCED_MOTION_TRANSITION: Transition = {
  duration: 0.01,
};

/**
 * The transition a surface should ENTER with, given the user's motion
 * preference and what kind of surface it is. `'lightbox'` (Dialog, Sheet,
 * AlertDialog) is the default so every existing call site keeps its 0.3s
 * response unchanged; `'menu'` (Popover, DropdownMenu and the rest of the
 * menu family, M2-03) is 0.2s.
 */
export function surfaceTransition(
  prefersReducedMotion: boolean | null,
  kind: 'lightbox' | 'menu' = 'lightbox',
): Transition {
  if (prefersReducedMotion) return REDUCED_MOTION_TRANSITION;
  return kind === 'menu' ? MENU_SPRING : SURFACE_SPRING;
}

/**
 * The transition a surface should EXIT with (M2-03/M2-04) - always the
 * shorter 0.2s response regardless of what it entered on, so a lightbox
 * opens slower than it closes and a menu's open and close read the same.
 */
export function surfaceExitTransition(prefersReducedMotion: boolean | null): Transition {
  return prefersReducedMotion ? REDUCED_MOTION_TRANSITION : SURFACE_SPRING_EXIT;
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

/**
 * Pass as `onUpdate` on a `motion.div` animating `opacity` to keep motion/react
 * on its own JS ticker instead of handing the animation to the browser's
 * native Web Animations API.
 *
 * motion-dom's `supportsBrowserAnimation` (node_modules/motion-dom/dist/es/animation/waapi/supports/waapi.mjs)
 * accelerates `opacity` (and other values in its `acceleratedValues` set, but
 * not `scale`/`x`/`y`, which motion tracks as their own motion values) via
 * WAAPI whenever nothing reads the value every frame (`!onUpdate`). WAAPI's
 * own `onfinish` handler (node_modules/motion-dom/dist/es/animation/NativeAnimation.mjs)
 * writes the settled value through `motionValue.set()` - which only takes
 * effect on motion's next scheduled render tick - and THEN calls
 * `this.animation.cancel()` synchronously, which strips the WAAPI effect
 * immediately. Cancelling before the settled value has been flushed to the
 * inline style leaves the element on whatever inline opacity was set before
 * this animation phase started, for that one frame: `0` (the pre-entrance
 * value) on enter, `1` (the pre-exit, fully-open value) on exit - which is
 * exactly what a real-browser frame trace showed: content dropped to
 * `opacity: 0` moments after its enter reached 1, and both content and
 * overlay flashed back to `opacity: 1` (darker than the surface was at any
 * point while open) on the frame before AnimatePresence unmounted them. It
 * never reproduces in jsdom, which has no WAAPI and always takes the JS path
 * this constant forces everywhere.
 *
 * A live `onUpdate` disqualifies WAAPI acceleration outright (motion has no
 * way to read a WAAPI-driven value every frame), so a no-op callback is enough
 * to keep the whole animation - and its settle-then-cancel bookkeeping - on
 * the main thread, where the DOM write and the animation's own lifecycle stay
 * in the same synchronous step.
 */
export const NOOP_ON_UPDATE = () => {};

export { useReducedMotion };
export type { Transition };
