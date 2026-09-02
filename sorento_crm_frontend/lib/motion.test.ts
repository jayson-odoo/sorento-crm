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
import {
  MENU_SPRING,
  REDUCED_MOTION_TRANSITION,
  SURFACE_SPRING,
  SURFACE_SPRING_EXIT,
  surfaceExitTransition,
  surfaceTransition,
  surfaceVariants,
} from './motion';

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

/**
 * M2-03 - the menu family (Popover, DropdownMenu, ContextMenu, HoverCard,
 * Menubar) opens/closes faster than a lightbox (Dialog, Sheet, AlertDialog),
 * and every surface closes on the same shorter response it opened on for a
 * menu, or a shorter one than it opened on for a lightbox.
 */
describe('surfaceTransition(kind) picks the menu preset (M2-03)', () => {
  it('defaults to the lightbox spring when no kind is passed', () => {
    expect(surfaceTransition(false)).toBe(SURFACE_SPRING);
  });

  it('returns the lightbox spring for kind "lightbox"', () => {
    expect(surfaceTransition(false, 'lightbox')).toBe(SURFACE_SPRING);
  });

  it('returns the menu spring for kind "menu"', () => {
    expect(surfaceTransition(false, 'menu')).toBe(MENU_SPRING);
    expect(MENU_SPRING).toMatchObject({ type: 'spring', bounce: 0, visualDuration: 0.2 });
  });

  it('collapses both kinds to the same reduced-motion transition', () => {
    expect(surfaceTransition(true, 'lightbox')).toBe(REDUCED_MOTION_TRANSITION);
    expect(surfaceTransition(true, 'menu')).toBe(REDUCED_MOTION_TRANSITION);
  });
});

describe('surfaceExitTransition (M2-03)', () => {
  it('returns the shorter exit spring when motion is not reduced', () => {
    expect(surfaceExitTransition(false)).toBe(SURFACE_SPRING_EXIT);
    expect(surfaceExitTransition(null)).toBe(SURFACE_SPRING_EXIT);
    expect(SURFACE_SPRING_EXIT).toMatchObject({ type: 'spring', bounce: 0, visualDuration: 0.2 });
  });

  it('collapses to the reduced-motion transition', () => {
    expect(surfaceExitTransition(true)).toBe(REDUCED_MOTION_TRANSITION);
  });
});
