/**
 * Image layer mirroring (PRICETAG-DESIGNER-GAPS item 1).
 *
 * `flipX` mirrors left-right, `flipY` top-bottom, both about the layer's own
 * box, so a flipped picture stays exactly where it was placed. Absent flags
 * mean "not flipped": every document saved before this draws unchanged. The
 * canvas (Konva) and the print page (DOM/CSS) each read the flags through one
 * helper below, so the two cannot mirror differently.
 */

export interface ImageFlip {
  flipX?: boolean;
  flipY?: boolean;
}

/** The CSS `transform` for the print page, or undefined when not flipped. */
export function cssFlipTransform(flip: ImageFlip): string | undefined {
  if (!flip.flipX && !flip.flipY) return undefined;
  return `scale(${flip.flipX ? -1 : 1}, ${flip.flipY ? -1 : 1})`;
}

/**
 * The Konva Group attributes that mirror a `w` x `h` box in place, or null
 * when not flipped. A negative scale mirrors about the origin, so the origin
 * moves to the far edge to keep the picture inside its box.
 */
export function konvaFlip(
  flip: ImageFlip,
  w: number,
  h: number,
): { x: number; y: number; scaleX: number; scaleY: number } | null {
  if (!flip.flipX && !flip.flipY) return null;
  return {
    x: flip.flipX ? w : 0,
    y: flip.flipY ? h : 0,
    scaleX: flip.flipX ? -1 : 1,
    scaleY: flip.flipY ? -1 : 1,
  };
}
