/**
 * PRICETAG-DESIGNER-GAPS item 3: feature icons.
 *
 * The ONE rule that picks and lays out a `feature_icons` layer's pictures, used by the editor
 * canvas, the request preview and the print page, so the three cannot disagree. Contract:
 * documentation/plans/dealer-kit/pricetag-feature-icons-contract.md F2.
 *
 * The rule lives on the spec VALUE (owner ruling 5 Nov 20:35): each value of a registry key carries
 * its own ordered icons, and the backend sends one `FeatureIcon` per (value, icon) in display
 * order (specs by their Icon order, values in the key's order, icons in the admin's order). The layer only
 * chooses which product it reads, the size, spacing and alignment.
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
 * cannot silently drop an icon; a spec row with no `raw` matches nothing. The order is the order
 * the icons came in: the registry's one sequence (spec Icon order, then the value's own list,
 * owner 5 Nov 21:0x). An asset reached twice shows once, at its first position.
 */
export function featureIconsFor(
  specs: readonly Pick<TagSpecValue, 'key' | 'raw'>[] | null | undefined,
  icons: readonly FeatureIcon[] | null | undefined,
): FeatureIcon[] {
  if (!specs?.length || !icons?.length) return [];
  const rawByKey = new Map<string, string>();
  for (const spec of specs) {
    if (spec.raw != null && !rawByKey.has(spec.key)) rawByKey.set(spec.key, spec.raw);
  }
  const out: FeatureIcon[] = [];
  const seen = new Set<string>();
  for (const icon of icons) {
    const raw = rawByKey.get(icon.spec_key);
    if (raw === undefined || !icon.values.includes(raw) || seen.has(icon.id)) continue;
    out.push(icon);
    seen.add(icon.id);
  }
  return out;
}

/**
 * PRICETAG-UPGRADE-VARIANTS S3: a family tag's icons on "All variants": every icon any member's
 * specs give (`featureIconsFor` per member), each once, in the input `icons` order (the registry's
 * one sequence). The caller passes the line product's own specs first and then each live, ticked
 * member's; the payload already left out discontinued, inactive and unticked members.
 */
export function variantFeatureIcons(
  memberSpecs: readonly (readonly Pick<TagSpecValue, 'key' | 'raw'>[] | null | undefined)[],
  icons: readonly FeatureIcon[] | null | undefined,
): FeatureIcon[] {
  const hit = new Set<string>();
  for (const specs of memberSpecs) for (const icon of featureIconsFor(specs, icons)) hit.add(icon.id);
  const out: FeatureIcon[] = [];
  for (const icon of icons ?? []) {
    if (!hit.has(icon.id)) continue;
    out.push(icon);
    hit.delete(icon.id);
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
  const { shown } = featureIconFit(count, props, boxWidth_mm);
  if (shown === 0) return [];
  const size = props.iconSize_mm;
  const gap = Math.max(0, props.gap_mm);
  const total = shown * size + (shown - 1) * gap;
  const free = Math.max(0, boxWidth_mm - total);
  const start =
    props.align === 'center' ? free / 2 : props.align === 'right' ? free : 0;
  return Array.from({ length: shown }, (_, i) => start + i * (size + gap));
}

/**
 * How many of `count` icons fit ENTIRELY inside the box, and how many do not. The one count
 * `featureIconRow` draws from, so a warning about dropped icons can never disagree with the row
 * (crew pass, 5 Nov: a dropped icon must never be silent). Alignment does not change it.
 */
export function featureIconFit(
  count: number,
  props: Pick<FeatureIconsLayerProps, 'iconSize_mm' | 'gap_mm'>,
  boxWidth_mm: number,
): { shown: number; dropped: number } {
  const total = Math.max(0, count);
  const size = props.iconSize_mm;
  const gap = Math.max(0, props.gap_mm);
  if (total === 0 || !(size > 0)) return { shown: 0, dropped: total };
  // Tolerate float noise so an icon that exactly fills the box is kept.
  const EPS = 1e-9;
  let shown = 0;
  while (shown < total && (shown + 1) * size + shown * gap <= boxWidth_mm + EPS) shown += 1;
  return { shown, dropped: total - shown };
}
