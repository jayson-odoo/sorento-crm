/**
 * Live text reflow on resize (D8, S6).
 *
 * Konva's Transformer resizes by writing `scaleX`/`scaleY` on the node, not
 * a new width and height - fine for a shape, wrong for a text box: a scale
 * transform stretches the GLYPHS along with the box, so the font visibly
 * grows or shrinks while the handle is held, then snaps back to its real
 * size only once `onTransformEnd` reads the scale, converts it, and resets
 * it to 1.
 *
 * That snap is correct at the end but wrong for the whole drag - the box
 * looks distorted the entire time it is held. The fix runs the SAME
 * conversion on every `onTransform` tick, not only at the end: read the
 * live scale, fold it into `width`/`height`, reset the scale to 1. Konva then
 * re-wraps the text at its fixed `fontSize` inside the new box on every
 * frame, so the drag itself reflows instead of only the release.
 *
 * This is the one multiplication both handlers need, pulled out so they
 * cannot drift from each other.
 */

export interface ReflowedSize {
  width: number;
  height: number;
}

/**
 * Fold a Konva scale into a concrete size. Takes the absolute value: dragging
 * a handle past the box's opposite edge flips Konva's scale sign, and a box
 * never has negative width or height.
 */
export function reflowedTextSize(
  width: number,
  height: number,
  scaleX: number,
  scaleY: number,
): ReflowedSize {
  return {
    width: Math.abs(width * scaleX),
    height: Math.abs(height * scaleY),
  };
}
