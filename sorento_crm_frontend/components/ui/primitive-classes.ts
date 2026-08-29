/**
 * Class strings shared by more than one primitive.
 *
 * Three lightbox surfaces (dialog, alert dialog, sheet) and seven controls
 * (button, checkbox, switch, radio, toggle, tab trigger, slider thumb) have to
 * agree on the scrim, the pressed state and the touch target. Written once here
 * so they cannot drift apart one file at a time.
 *
 * See documentation/plans/design-system/PLAN-apple-alignment.md 3.6 and UAC
 * S1-02, S1-09, S1-10.
 */

/**
 * The one scrim: 50% black with an 8px blur, faded in and out with the surface.
 *
 * `prefers-reduced-transparency` has no Tailwind variant, hence the arbitrary
 * media query: under it the blur is off and the scrim goes to 72% so the
 * surface still separates from the page behind it.
 */
export const OVERLAY_CLASS =
  'fixed inset-0 z-50 bg-black/50 backdrop-blur-md ' +
  'data-[state=open]:animate-in data-[state=closed]:animate-out ' +
  'data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 ' +
  '[@media(prefers-reduced-transparency:reduce)]:backdrop-blur-none ' +
  '[@media(prefers-reduced-transparency:reduce)]:bg-black/72';

/**
 * Pressed feedback: the control answers on pointer DOWN, not on release.
 *
 * A 3% shrink is enough to read as a physical press at every control size, and
 * it is suppressed for anyone who asked for less motion.
 */
export const PRESSED_CLASS =
  'transition-[transform,color,background-color,border-color,box-shadow] ' +
  'active:scale-[0.97] motion-reduce:active:scale-100';

/**
 * A 44x44 touch target on a coarse pointer, without changing the rendered size.
 *
 * The target is an invisible centred pseudo-element, so a 20px checkbox stays a
 * 20px checkbox and still catches a thumb. `relative` is on the control itself
 * (every primitive that uses this already sets it or is added here).
 */
export const COARSE_HIT_TARGET_CLASS =
  'relative pointer-coarse:after:absolute pointer-coarse:after:left-1/2 pointer-coarse:after:top-1/2 ' +
  'pointer-coarse:after:h-full pointer-coarse:after:w-full ' +
  'pointer-coarse:after:min-h-11 pointer-coarse:after:min-w-11 ' +
  'pointer-coarse:after:-translate-x-1/2 pointer-coarse:after:-translate-y-1/2 ' +
  "pointer-coarse:after:content-['']";
