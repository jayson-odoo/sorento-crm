/**
 * Feature icons that a tag sheet will NOT print because their layer box is too narrow (crew pass,
 * 5 Nov: a dropped icon must never be silent). Walks the sheet the way the print page does: each
 * placed tag, each visible feature icons layer that prints for that data, its subject's specs,
 * then `featureIconsFor` + `featureIconFit`, the same two functions the renderers draw with.
 */
import { featureIconFit, type FeatureIcon } from './feature-icons';
import { layerFeatureIcons, layerShownFor } from './product-block';
import type { LineTagData, TagBindingData, TagSheetDoc } from './tag-template-types';

/** One tag that loses icons: its label (`2a`, never an id) and how many. */
export interface FeatureIconDrop {
  tagLabel: string;
  dropped: number;
}

/** What the helper reads off a tag's resolved data (a `LineTagData` or the print payload row). */
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

export function featureIconDrops(
  doc: TagSheetDoc | null | undefined,
  dataFor: (requestTagId: string) => TagData | null | undefined,
  featureIcons: readonly FeatureIcon[] | null | undefined,
  assetUrls: Record<string, string> | null | undefined,
): FeatureIconDrop[] {
  if (!doc || !featureIcons?.length) return [];
  const out: FeatureIconDrop[] = [];
  for (const sheet of doc.sheets ?? []) {
    for (const tag of sheet.tags ?? []) {
      const data = dataFor(tag.request_tag_id);
      if (!data) continue;
      const binding = bindingOf(data);
      let dropped = 0;
      for (const layer of tag.layers ?? []) {
        if (layer.props?.kind !== 'feature_icons' || layer.visible === false) continue;
        if (!layerShownFor(layer, binding)) continue;
        // Only icons that would draw: one with no signed URL is skipped by the renderers anyway.
        const icons = layerFeatureIcons(binding, layer, featureIcons).filter(
          (icon) => assetUrls?.[icon.id],
        );
        dropped += featureIconFit(icons.length, layer.props, layer.width_mm).dropped;
      }
      if (dropped > 0) out.push({ tagLabel: data.tag_label || '?', dropped });
    }
  }
  return out;
}
