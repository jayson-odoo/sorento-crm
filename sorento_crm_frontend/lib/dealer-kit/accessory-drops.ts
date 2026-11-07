/**
 * PRICETAG-ACCESSORIES (A6): accessories a tag sheet will NOT print because their box is too
 * small, per tag. Walks the sheet the way the print page does (each placed tag, each visible
 * accessories layer that prints for that data) and counts with `accessoryBoxLayout`, the same
 * function every renderer draws with. The `feature-icon-drops.ts` pattern.
 */
import { accessoriesOf, accessoryBoxLayout, accessoryLineCount } from './accessory-box';
import { cardDropped } from './accessory-card';
import { layerShownFor } from './product-block';
import type { LineTagData, TagBindingData, TagSheetDoc } from './tag-template-types';

/** One tag that loses accessories: its label (`2a`, never an id) and how many. */
export interface AccessoryDrop {
  tagLabel: string;
  dropped: number;
}

type TagData = Partial<LineTagData> & { tag_label?: string };

function bindingOf(data: TagData): TagBindingData {
  return {
    kind: 'line',
    line: {
      ...data,
      open_groups: data.open_groups ?? [],
      parts: data.parts ?? [],
      specs: data.specs ?? [],
      images: data.images ?? [],
    } as LineTagData,
  };
}

export function accessoryDrops(
  doc: TagSheetDoc | null | undefined,
  dataFor: (requestTagId: string) => TagData | null | undefined,
): AccessoryDrop[] {
  if (!doc) return [];
  const out: AccessoryDrop[] = [];
  for (const sheet of doc.sheets ?? []) {
    for (const tag of sheet.tags ?? []) {
      const data = dataFor(tag.request_tag_id);
      if (!data) continue;
      const binding = bindingOf(data);
      let dropped = 0;
      for (const layer of tag.layers ?? []) {
        if (layer.props?.kind !== 'accessories' || layer.visible === false) continue;
        if (!layerShownFor(layer, binding)) continue;
        const items = accessoriesOf(binding, layer);
        dropped += layer.props.card
          ? cardDropped(items.length, layer.props, layer.width_mm, layer.height_mm)
          : accessoryBoxLayout(
              items.length,
              layer.props,
              layer.width_mm,
              layer.height_mm,
              accessoryLineCount(items),
            ).dropped;
      }
      if (dropped > 0) out.push({ tagLabel: data.tag_label || '?', dropped });
    }
  }
  return out;
}
