/**
 * PRICETAG-DESIGNER-GAPS item 3: feature icons.
 *
 * The ONE rule that picks and lays out a `feature_icons` layer's pictures, used by the editor
 * canvas, the request preview and the print page, so the three cannot disagree. Contract:
 * documentation/plans/dealer-kit/pricetag-feature-icons-contract.md F2.
 *
 * The rule lives on the spec VALUE (owner ruling 5 Nov 20:35): each value of a registry key carries
 * its own ordered icons, and the backend sends one `FeatureIcon` per (value, icon) in display
 * order (keys by spec key, values in the key's order, icons in the admin's order). The layer only
 * chooses which product it reads, the size, spacing, alignment and the designer's order.
 */
import type {
  FeatureIconsLayerProps,
  TagSpecValue,
} from './tag-template-types';

/** One icon of one spec value: shown when the product's `spec_key` reads one of `values`. */
export interface FeatureIcon {
  id: string;
  name: string;
  spec_key: string;
  values: string[];
}

/**
 * The icons whose rule matches these specs, in display order.
 *
 * A rule matches on the spec's RAW stored value, never its display text, so renaming a label
 * cannot silently drop an icon; a spec row with no `raw` matches nothing. Ids in `order` come
 * first, in that order; the rest keep the order they came in (the admin's order on the spec
 * value, owner ruling 5 Nov 20:4x). Each icon appears at most once, at its first position.
 */
export function featureIconsFor(
  specs: readonly Pick<TagSpecValue, 'key' | 'raw'>[] | null | undefined,
  icons: readonly FeatureIcon[] | null | undefined,
  order: readonly string[] = [],
): FeatureIcon[] {
  if (!specs?.length || !icons?.length) return [];
  const rawByKey = new Map<string, string>();
  for (const spec of specs) {
    if (spec.raw != null && !rawByKey.has(spec.key))
      rawByKey.set(spec.key, spec.raw);
  }
  const matched = icons.filter((icon) => {
    const raw = rawByKey.get(icon.spec_key);
    return raw !== undefined && icon.values.includes(raw);
  });

  return orderedIcons(matched, order);
}

/**
 * Icons in display order: ids in `order` first, in that order, then the rest in the order they
 * came in (never by name). Each icon at most once, at its first position; an id in `order` that
 * is not among `icons` is ignored. The inspector lists the library this way, so its list reads
 * the same as the row it prints.
 */
export function orderedIcons(
  icons: readonly FeatureIcon[],
  order: readonly string[] = [],
): FeatureIcon[] {
  const byId = new Map<string, FeatureIcon>();
  for (const icon of icons) if (!byId.has(icon.id)) byId.set(icon.id, icon);
  const out: FeatureIcon[] = [];
  const seen = new Set<string>();
  for (const id of order) {
    const icon = byId.get(id);
    if (icon && !seen.has(id)) {
      out.push(icon);
      seen.add(id);
    }
  }
  for (const icon of icons) {
    if (seen.has(icon.id)) continue;
    out.push(icon);
    seen.add(icon.id);
  }
  return out;
}

/**
 * The left edge (mm, inside the layer box) of each icon in a packed row.
 *
 * Icons are `iconSize_mm` wide and `gap_mm` apart with no holes for missing facts. As many as
 * fit ENTIRELY inside `boxWidth_mm` are kept (the array is shorter than `count` otherwise), then
 * the kept row is aligned left, centre or right. Vertically each icon is centred in the box:
 * `y = (height - iconSize) / 2`.
 */
export function featureIconRow(
  count: number,
  props: Pick<FeatureIconsLayerProps, 'iconSize_mm' | 'gap_mm' | 'align'>,
  boxWidth_mm: number,
): number[] {
  const size = props.iconSize_mm;
  const gap = Math.max(0, props.gap_mm);
  if (count <= 0 || !(size > 0) || boxWidth_mm < size) return [];
  // Tolerate float noise so an icon that exactly fills the box is kept.
  const EPS = 1e-9;
  let kept = 0;
  while (kept < count && (kept + 1) * size + kept * gap <= boxWidth_mm + EPS)
    kept += 1;
  if (kept === 0) return [];
  const total = kept * size + (kept - 1) * gap;
  const free = Math.max(0, boxWidth_mm - total);
  const start =
    props.align === 'center' ? free / 2 : props.align === 'right' ? free : 0;
  return Array.from({ length: kept }, (_, i) => start + i * (size + gap));
}
