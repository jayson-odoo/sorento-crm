/**
 * Pure helpers behind the B/I/U/S shortcuts (S2, D4/D10).
 *
 * Bold is not a boolean: it toggles `fontWeight`, the same value the Font
 * Weight select edits, so the two never disagree about what "bold" means on
 * a layer. Italic, underline and strikethrough ARE booleans
 * (`TextLayerProps.italic/underline/strikethrough`), applied to every
 * targeted layer at once so one keypress is one history entry.
 */
import type { TagLayer, TextLayerProps } from './tag-template-types';

/** The three whole-layer boolean flags a text layer can carry (D4). */
export type TextFormatFlag = 'italic' | 'underline' | 'strikethrough';

/**
 * `>= 600` reads as already-bold and drops to regular; anything below,
 * including the 500 "Medium" weight, goes to 700 (D10).
 */
export function toggleBold(weight: number): number {
  return weight >= 600 ? 400 : 700;
}

/**
 * Applies `flag` to every text layer in `ids`, all landing on the SAME
 * target state: on if any targeted layer was missing it, off only when every
 * targeted layer already had it. A layer saved before this flag existed
 * reads as false (AC-S2-9), so it counts toward "not all true" and the first
 * press turns the flag on everywhere.
 *
 * Non-text layers and ids not present are left untouched.
 */
export function toggleTextFlag(
  layers: TagLayer[],
  ids: string[],
  flag: TextFormatFlag,
): TagLayer[] {
  const targets = new Set(ids);
  const targeted = layers.filter(
    (layer): layer is TagLayer & { props: TextLayerProps } =>
      targets.has(layer.id) && layer.props.kind === 'text',
  );
  if (targeted.length === 0) return layers;

  const allTrue = targeted.every((layer) => Boolean(layer.props[flag]));
  const next = !allTrue;

  return layers.map((layer) => {
    if (!targets.has(layer.id) || layer.props.kind !== 'text') return layer;
    return { ...layer, props: { ...layer.props, [flag]: next } };
  });
}
