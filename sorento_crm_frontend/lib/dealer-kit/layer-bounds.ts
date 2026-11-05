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

interface Size {
  width_mm: number;
  height_mm: number;
}

function outside(layer: TagLayer, size: Size): boolean {
  return (
    layer.x_mm + layer.width_mm > size.width_mm + EPSILON_MM ||
    layer.y_mm + layer.height_mm > size.height_mm + EPSILON_MM
  );
}

/**
 * The layers a resize newly cuts off: inside the old size, outside the new one.
 * A layer that already stuck out before is not news (crew browser pass, 5 Nov:
 * growing a template still "warned" about a layer that was already outside).
 */
export function layersCutOff(layers: TagLayer[], before: Size, after: Size): number {
  return layers.filter(
    (layer) => layer.type !== 'group' && !outside(layer, before) && outside(layer, after),
  ).length;
}
