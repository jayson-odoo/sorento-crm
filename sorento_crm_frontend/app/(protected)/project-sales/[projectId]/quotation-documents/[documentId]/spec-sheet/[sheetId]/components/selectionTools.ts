import type {
  TagLayer,
  TagLayerProps,
} from '@/lib/dealer-kit/tag-template-types';

import type { ApplyAllChanges } from '../../../../../../_shared/services/specSheetService';

/**
 * What "Apply to every page" may carry. The same keys the server accepts: where a layer sits,
 * how big it is, turned, stacked and shown, and its STYLE. Never what it says or binds.
 */
const TOP_KEYS = [
  'x_mm',
  'y_mm',
  'width_mm',
  'height_mm',
  'rotation_deg',
  'z_index',
  'visible',
] as const;
const PROP_KEYS = new Set([
  'fontFamily',
  'fontSize',
  'fontWeight',
  'color',
  'align',
  'lineHeight',
  'letterSpacing',
  'italic',
  'underline',
  'strikethrough',
  'fit',
  'fill',
  'stroke',
  'strokeWidth',
  'cornerRadius',
  'maskShape',
]);

/** The part of an inspector change that may go to every page, or null when none of it may. */
export function applicableChanges(
  top: Partial<TagLayer> | null,
  props: Partial<TagLayerProps> | null,
): ApplyAllChanges | null {
  const out: ApplyAllChanges = {};
  for (const key of TOP_KEYS) {
    const value = top?.[key];
    if (value !== undefined && value !== null)
      (out as Record<string, unknown>)[key] = value;
  }
  const style: Record<string, string | number | boolean> = {};
  for (const [key, value] of Object.entries(props ?? {})) {
    if (
      PROP_KEYS.has(key) &&
      (typeof value === 'string' ||
        typeof value === 'number' ||
        typeof value === 'boolean')
    ) {
      style[key] = value;
    }
  }
  if (Object.keys(style).length > 0) out.props = style;
  return Object.keys(out).length > 0 ? out : null;
}
