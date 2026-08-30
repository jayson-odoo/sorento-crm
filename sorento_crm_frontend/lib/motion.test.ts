/**
 * S8-01 - the shared spring collapses under `prefers-reduced-motion: reduce`.
 *
 * Dialog, Sheet, Popover and DropdownMenu all resolve their open/close
 * transition through `surfaceTransition` and their initial/animate/exit
 * targets through `surfaceVariants` - pinning the branch here, once, is what
 * proves all four collapse to the same near-instant fade rather than each
 * primitive inventing its own reduced-motion escape hatch.
 */
import { describe, expect, it } from 'vitest';
import { REDUCED_MOTION_TRANSITION, SURFACE_SPRING, surfaceTransition, surfaceVariants } from './motion';

describe('Shared surface spring collapses under reduced motion (S8-01)', () => {
  it('uses the critically damped spring when motion is not reduced', () => {
    expect(surfaceTransition(false)).toBe(SURFACE_SPRING);
    expect(surfaceTransition(null)).toBe(SURFACE_SPRING);
    expect(SURFACE_SPRING).toMatchObject({ type: 'spring', bounce: 0 });
  });

  it('collapses to a same-frame transition when the user asked for less motion', () => {
    expect(surfaceTransition(true)).toBe(REDUCED_MOTION_TRANSITION);
    expect(REDUCED_MOTION_TRANSITION.type).not.toBe('spring');
    expect(REDUCED_MOTION_TRANSITION.duration).toBeLessThanOrEqual(0.01);
  });

  it('scales up from the trigger when motion is not reduced', () => {
    const variants = surfaceVariants(false);
    expect(variants.initial).toMatchObject({ opacity: 0, scale: 0.96 });
    expect(variants.animate).toMatchObject({ opacity: 1, scale: 1 });
    expect(variants.exit).toMatchObject({ opacity: 0, scale: 0.96 });
  });

  it('drops the scale under reduced motion and keeps only the fade', () => {
    const variants = surfaceVariants(true);
    expect(variants.initial).toStrictEqual({ opacity: 0 });
    expect(variants.animate).toStrictEqual({ opacity: 1 });
    expect(variants.exit).toStrictEqual({ opacity: 0 });
    expect(variants.initial).not.toHaveProperty('scale');
  });
});
