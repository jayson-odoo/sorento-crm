/**
 * PRICETAG-UPGRADE-VARIANTS FE test 6 (AC-F1, F2, F2b, F4, F5, F6): `variantFeatureIcons` and the
 * "All variants" feature icons layer.
 *
 * Written test-FIRST. `variantFeatureIcons(memberSpecs, icons)` lives in `./feature-icons`;
 * the layer reads `subjectSlot: { kind: 'variants' }`.
 */
import { describe, expect, it } from 'vitest';

import { featureIconsFor, variantFeatureIcons } from './feature-icons';
import { layerDisplay, subjectOf } from './product-block';
import { FAMILY_VARIANTS, familyLine, spec, TRAP_ICONS } from './test-support/upgrade-variants-fixtures';
import type { TagBindingData, TagLayer } from './tag-template-types';

const ids = (list: { id: string }[]) => list.map((i) => i.id);
const OWN = [spec('trap_length', '250', '250'), spec('trap_type', 'S Trap', 's_trap')];

describe('variantFeatureIcons', () => {
  it('shows the union of every member, each icon once, in the library order', () => {
    const members = [OWN, ...FAMILY_VARIANTS.map((v) => v.specs)];
    expect(ids(variantFeatureIcons(members, TRAP_ICONS))).toEqual(['i6', 'i8', 'i10', 'ip', 'iuf']);
  });

  it('keeps the input icons order whatever the member order', () => {
    const reversed = [...FAMILY_VARIANTS].reverse().map((v) => v.specs);
    expect(ids(variantFeatureIcons([...reversed, OWN], TRAP_ICONS))).toEqual(['i6', 'i8', 'i10', 'ip', 'iuf']);
    const swapped = [TRAP_ICONS[4], TRAP_ICONS[0], TRAP_ICONS[3], TRAP_ICONS[2], TRAP_ICONS[1]];
    expect(ids(variantFeatureIcons([OWN, ...FAMILY_VARIANTS.map((v) => v.specs)], swapped))).toEqual(
      ['iuf', 'i6', 'ip', 'i10', 'i8'],
    );
  });

  it('two members giving the same icon show it once (-SH and -SH-UF both 250mm)', () => {
    const out = variantFeatureIcons([OWN, [spec('trap_length', '250', '250')]], TRAP_ICONS);
    expect(ids(out)).toEqual(['i10']);
  });

  it('a leaf (no variants) is the line own icons', () => {
    expect(ids(variantFeatureIcons([OWN], TRAP_ICONS))).toEqual(ids(featureIconsFor(OWN, TRAP_ICONS)));
    expect(ids(variantFeatureIcons([OWN], TRAP_ICONS))).toEqual(['i10']);
  });

  it('a member holding nothing adds nothing; no members at all gives nothing', () => {
    expect(ids(variantFeatureIcons([[]], TRAP_ICONS))).toEqual([]);
    expect(variantFeatureIcons([], TRAP_ICONS)).toEqual([]);
  });

  it('unticking the 300mm member (not in the payload) leaves the other five icons (AC-F2b)', () => {
    const withUf300 = [...FAMILY_VARIANTS.map((v) => v.specs), [spec('trap_length', '300', '300')]];
    const icons = [...TRAP_ICONS, { id: 'i12', name: '12in S-trap 300mm', spec_key: 'trap_length', values: ['300'] }];
    expect(ids(variantFeatureIcons([OWN, ...withUf300], icons))).toContain('i12');
    expect(ids(variantFeatureIcons([OWN, ...FAMILY_VARIANTS.map((v) => v.specs)], icons))).not.toContain('i12');
  });
});

const layer = (subjectSlot?: unknown): TagLayer =>
  ({
    id: 'fi',
    type: 'feature_icons',
    x_mm: 0, y_mm: 0, width_mm: 60, height_mm: 8, rotation_deg: 0, z_index: 1, locked: false, visible: true,
    slot_binding: null, text_override: null,
    props: { kind: 'feature_icons', iconSize_mm: 6, gap_mm: 1, align: 'left', ...(subjectSlot ? { subjectSlot } : {}) },
  }) as unknown as TagLayer;

const URLS = Object.fromEntries(TRAP_ICONS.map((i) => [i.id, `https://cdn/${i.id}.png`]));
const iconIds = (display: unknown) => ((display as { icons?: { id: string }[] }).icons ?? []).map((i) => i.id);

describe('the "All variants" layer', () => {
  it('draws the union of the line own icons and every variant payload (AC-F2)', () => {
    const data = familyLine(FAMILY_VARIANTS);
    expect(iconIds(layerDisplay(layer({ kind: 'variants' }), data, URLS, TRAP_ICONS))).toEqual(['i6', 'i8', 'i10', 'ip', 'iuf']);
  });

  it('a layer without it still draws only the line own icons (AC-F8)', () => {
    const data = familyLine(FAMILY_VARIANTS);
    expect(iconIds(layerDisplay(layer(), data, URLS, TRAP_ICONS))).toEqual(['i10']);
    expect(iconIds(layerDisplay(layer({ kind: 'main' }), data, URLS, TRAP_ICONS))).toEqual(['i10']);
  });

  it('a leaf line (variants: []) shows only its own icons (AC-F5)', () => {
    const leaf = familyLine([], [spec('trap_length', '150', '150'), spec('trap_type', 'S Trap', 's_trap')]);
    expect(iconIds(layerDisplay(layer({ kind: 'variants' }), leaf, URLS, TRAP_ICONS))).toEqual(['i6']);
  });

  it('a row pinned before variants existed reads as no variants', () => {
    const data = familyLine(FAMILY_VARIANTS);
    if (data.kind === 'line') delete (data.line as never as Record<string, unknown>).variants;
    expect(iconIds(layerDisplay(layer({ kind: 'variants' }), data, URLS, TRAP_ICONS))).toEqual(['i10']);
  });

  it('works on the designer preview product too', () => {
    const line = familyLine(FAMILY_VARIANTS);
    if (line.kind !== 'line') throw new Error('fixture');
    const { specs, variants } = line.line as never as { specs: unknown[]; variants: unknown[] };
    const preview = {
      kind: 'product',
      product: { id: 'p', code: 'SRTWC8354-SH', name: 'WC', dimensions: '', spec_lines: [], specs, images: [],
        list_price: 1750, offer_price: 799, promotion_id: null, barcode: null, variants },
    } as unknown as TagBindingData;
    expect(iconIds(layerDisplay(layer({ kind: 'variants' }), preview, URLS, TRAP_ICONS))).toEqual(['i6', 'i8', 'i10', 'ip', 'iuf']);
  });

  it('subjectOf treats variants as the main subject for any other use (AC-F6)', () => {
    const data = familyLine(FAMILY_VARIANTS);
    if (data.kind !== 'line') throw new Error('fixture');
    (data.line as never as Record<string, unknown>).slots = {
      main: { product_id: 'id-main', code: 'SRTWC8354-SH', name: 'WC', dimensions: '', list_price: 1750 },
      fixed: [], groups: [], upgrades: [],
    };
    const viaVariants = subjectOf(data, layer({ kind: 'variants' }));
    const viaMain = subjectOf(data, layer({ kind: 'main' }));
    expect(viaVariants).toEqual(viaMain);
    expect(viaVariants?.kind === 'product' ? viaVariants.product.code : null).toBe('SRTWC8354-SH');
  });
});
