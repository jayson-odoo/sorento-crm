/**
 * How many layers a template size would cut off (PRICETAG-DESIGNER-GAPS item 4).
 *
 * Resizing a template keeps every layer exactly where it is (AC-S1-5 of the
 * size control), so a smaller size can leave layers hanging off the edge. The
 * resize warning names how many. A group's box is the union of its children,
 * so groups are skipped: each child is counted on its own, once.
 */
import type { TagLayer } from './tag-template-types';

/** Under a hundredth of a millimetre is float noise, not a layer off the edge. */
const EPSILON_MM = 0.01;

export function layersOutside(layers: TagLayer[], width_mm: number, height_mm: number): number {
  return layers.filter(
    (layer) =>
      layer.type !== 'group' &&
      (layer.x_mm + layer.width_mm > width_mm + EPSILON_MM ||
        layer.y_mm + layer.height_mm > height_mm + EPSILON_MM),
  ).length;
}
