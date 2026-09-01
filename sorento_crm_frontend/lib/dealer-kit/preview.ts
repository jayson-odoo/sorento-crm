/**
 * Which product each BLOCK of a template is being looked at with (D53).
 *
 * Preview exists because a template ships UNBOUND: every slot is a placeholder
 * until a request binds it, so there is nothing to look at unless the editor
 * lends the canvas some real data. D41 lent it one product and gave that same
 * product to every layer, which is right for a one-product tag and wrong for
 * the sink combo, where a main sink and three alternative taps are four
 * different products on one piece of paper.
 *
 * So the preview is a map keyed by block, and this module is the arithmetic
 * over it: which blocks may be previewed, what to call them so a person can
 * tell three identical alternatives apart, and which binding one layer
 * resolves against. No React, no Konva, no fetching.
 *
 * NONE of this is ever written into `layers`. Preview is editor state that dies
 * with the component, which is the whole point: looking at a template with real
 * data must not quietly bind it.
 */

import type { GroupBinding, SlotBinding, TagLayer } from './tag-template-types';
import { layerDisplayName } from './product-block';

/** Whether a block wants a product or a set. Mirrors the picker's own modes. */
export type PreviewMode = 'product' | 'set';

/** One block the user may point at a product. */
export interface PreviewableBlock {
  groupId: string;
  /** How the block is named in the picker and the Inspector. Never an id. */
  label: string;
  mode: PreviewMode;
}

/** Chosen preview per block: `groupId -> binding`. */
export type PreviewMap = Record<string, GroupBinding>;

/**
 * The synthesized block over every loose (ungrouped) bound layer (D10, S6).
 *
 * Never a real layer id, so it can never collide with one - `groupId` on a
 * real block always comes off a `TagLayer.id`, which this deliberately is
 * not.
 */
export const WHOLE_TAG_BLOCK_ID = '__whole_tag__';

/**
 * The slots that make a block ABOUT a product or a set.
 *
 * `badges`, `alternatives` and `accessories` are missing on purpose: they name
 * other products, not this one, so a block whose only slot is one of them has
 * nothing of its own to resolve.
 */
const PRODUCT_SLOTS: SlotBinding[] = [
  'product_image',
  'code',
  'name',
  'dimensions',
  'spec_lines',
  'list_price',
  'sell_price',
  'set_members',
  'included_accessories',
];

/** The `binding` a group carries. Null in the document means "not bindable". */
function bindingOfGroup(layer: TagLayer): GroupBinding | null | undefined {
  return layer.props.kind === 'group'
    ? (layer.props as { binding?: GroupBinding | null }).binding
    : undefined;
}

/**
 * Every block the user may preview, in document order.
 *
 * Two conditions, and the second one is the interesting half. A group has to
 * hold a slot that resolves against a product, AND it must not be written
 * `binding: null`. The seed uses that null to say a block is not about a
 * product at all: the accessories strip's title carries `included_accessories`
 * - a real product field - so the slot test alone would offer a product picker
 * for a strip of pictures that can never hold one.
 */
export function previewableBlocks(layers: TagLayer[]): PreviewableBlock[] {
  const byId = new Map(layers.map((layer) => [layer.id, layer]));
  const blocks: PreviewableBlock[] = [];

  for (const layer of layers) {
    if (layer.props.kind !== 'group') continue;
    if (bindingOfGroup(layer) === null) continue;

    const children = layer.props.children
      .map((id) => byId.get(id))
      .filter((child): child is TagLayer => Boolean(child));
    const slots = children
      .map((child) => child.slot_binding)
      .filter((slot): slot is SlotBinding => PRODUCT_SLOTS.includes(slot));
    if (slots.length === 0) continue;

    blocks.push({
      groupId: layer.id,
      label: blockLabel(layer, children, blocks.length + 1),
      mode: slots.includes('set_members') ? 'set' : 'product',
    });
  }

  return blocks;
}

/**
 * What to call a block in the picker and the Inspector.
 *
 * The Layers panel's own name is the start, because that is what the block is
 * already called on screen. It is not enough on its own: three unbound
 * alternatives all read `Group (5)`, so the block's position in the document
 * and the placeholder its `code` child carries are appended. Position is what
 * actually separates them; the placeholder is what makes a designed block
 * recognisable once somebody types over it.
 */
function blockLabel(group: TagLayer, children: TagLayer[], ordinal: number): string {
  const code = children.find((child) => child.slot_binding === 'code');
  const placeholder =
    code?.text_override ?? (code?.props.kind === 'text' ? code.props.text : null);
  const trailing = placeholder?.trim() ? ` - ${placeholder.trim()}` : '';
  return `${layerDisplayName(group)} - block ${ordinal}${trailing}`;
}

/** Every layer with a bindable slot that no group has claimed. */
function looseBoundLayers(layers: TagLayer[]): TagLayer[] {
  const claimed = new Set<string>();
  for (const layer of layers) {
    if (layer.props.kind !== 'group') continue;
    for (const childId of layer.props.children) claimed.add(childId);
  }
  return layers.filter(
    (layer) =>
      layer.props.kind !== 'group' &&
      !claimed.has(layer.id) &&
      layer.slot_binding !== null &&
      PRODUCT_SLOTS.includes(layer.slot_binding),
  );
}

/**
 * ONE implicit block over every loose (ungrouped) bound layer (D10).
 *
 * A template built without `Ctrl+G` still deserves an eye: the frame carries
 * it, standing in for a group that was never made. Absent when nothing on
 * the tag is bindable at all - not every unbound layer, only slot-bound ones
 * (`PRODUCT_SLOTS`) count, the same rule a real block is held to.
 */
export function wholeTagBlock(layers: TagLayer[]): PreviewableBlock | null {
  const loose = looseBoundLayers(layers);
  if (loose.length === 0) return null;
  return {
    groupId: WHOLE_TAG_BLOCK_ID,
    label: 'Whole tag',
    mode: loose.some((layer) => layer.slot_binding === 'set_members') ? 'set' : 'product',
  };
}

/** The previewable block a layer belongs to, itself included. */
export function previewBlockOf(
  layer: TagLayer,
  blocks: PreviewableBlock[],
  groupOfChild: Map<string, TagLayer>,
): PreviewableBlock | null {
  const owner = layer.props.kind === 'group' ? layer : groupOfChild.get(layer.id);
  if (!owner) return null;
  return blocks.find((block) => block.groupId === owner.id) ?? null;
}

/**
 * The preview binding this layer draws against, or nothing.
 *
 * "Or nothing" is deliberate: this answers only what the PREVIEW says, and the
 * caller falls back to whatever the document itself binds. That keeps the one
 * rule worth pinning in a test free of the document's own binding, and it is
 * what lets the request designer keep drawing its line while one block of the
 * tag is previewed against something else.
 *
 * A slot-bound layer that belongs to no group follows the implicit
 * `WHOLE_TAG_BLOCK_ID` entry (D10, S6) - one product choice for every loose
 * end of the tag, from the frame's own eye, rather than piggy-backing on
 * whichever real block happened to be previewed first.
 */
export function previewBindingFor(
  layer: TagLayer,
  previews: PreviewMap,
  groupOfChild: Map<string, TagLayer>,
): GroupBinding | undefined {
  const owner = layer.props.kind === 'group' ? layer : groupOfChild.get(layer.id);
  if (owner) return previews[owner.id];

  if (!layer.slot_binding || !PRODUCT_SLOTS.includes(layer.slot_binding)) return undefined;
  return previews[WHOLE_TAG_BLOCK_ID];
}
