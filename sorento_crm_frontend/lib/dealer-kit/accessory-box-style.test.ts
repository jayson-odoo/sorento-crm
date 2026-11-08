/**
 * PRICETAG-ACCESSORY-DESIGNER S6: `accessoryBoxStyleOf(data, layer)` in `./accessory-card` resolves the
 * box style a product or combo names, branching exactly like `accessoriesOf`:
 *   line -> line.accessory_box_style; product preview with a combo -> the combo's (never the product's);
 *   without a combo -> the product's; subjectSlot -> that slot part's; subjectPart -> that part's
 *   (-1 = the main product's slot row). Null when there is none.
 * Written test-FIRST.
 */
import { describe, expect, it } from 'vitest';

import { accessoryBoxStyleOf, applyAccessoryDesign, accessoryDesign } from './accessory-card';
import { defaultAccessoriesProps, type AccessoriesLayerProps } from './tag-template-types';

const style = (id: string, headerText = id) => ({ id, name: `Style ${id}`, design: { headerText, direction: 'horizontal' } });
const LINE_S = style('line');
const COMBO_S = style('combo');
const PRODUCT_S = style('product');
const MAIN_S = style('main');
const FIXED_S = style('fixed');
const PICK_S = style('pick');
const UPGRADE_S = style('upgrade');
const PART_S = style('part');

const layer = (over: Record<string, unknown> = {}) => ({ props: { ...defaultAccessoriesProps(), ...over } });
const productData = (product: Record<string, unknown>) => ({ kind: 'product', product }) as never;
const lineData = (line: Record<string, unknown>) => ({ kind: 'line', line }) as never;

const slots = {
  main: { accessory_box_style: MAIN_S },
  fixed: [{ accessory_box_style: FIXED_S }],
  groups: [{ role: 'Tap', size: 1, picks: [{ accessory_box_style: PICK_S }] }],
  upgrades: [{ accessory_box_style: UPGRADE_S }],
};

describe('accessoryBoxStyleOf', () => {
  it('a request line reads the line\'s own (already resolved) style', () => {
    expect(accessoryBoxStyleOf(lineData({ accessory_box_style: LINE_S, accessories: [], parts: [] }), layer())).toEqual(LINE_S);
  });

  it('a product preview with a combo reads the combo\'s style, never the product\'s', () => {
    const data = productData({ accessory_box_style: PRODUCT_S, combo: { accessory_box_style: COMBO_S } });
    expect(accessoryBoxStyleOf(data, layer())).toEqual(COMBO_S);
    const comboWithNone = productData({ accessory_box_style: PRODUCT_S, combo: { accessory_box_style: null } });
    expect(accessoryBoxStyleOf(comboWithNone, layer())).toBeNull();
  });

  it('a product preview without a combo reads the product\'s style', () => {
    expect(accessoryBoxStyleOf(productData({ accessory_box_style: PRODUCT_S, combo: null }), layer())).toEqual(PRODUCT_S);
  });

  it('a layer pointed at a position reads that slot part\'s style', () => {
    const data = productData({ accessory_box_style: PRODUCT_S, combo: { accessory_box_style: COMBO_S }, slots });
    expect(accessoryBoxStyleOf(data, layer({ subjectSlot: { kind: 'main' } }))).toEqual(MAIN_S);
    expect(accessoryBoxStyleOf(data, layer({ subjectSlot: { kind: 'fixed', index: 0 } }))).toEqual(FIXED_S);
    expect(accessoryBoxStyleOf(data, layer({ subjectSlot: { kind: 'pick', group: 0, index: 0 } }))).toEqual(PICK_S);
    expect(accessoryBoxStyleOf(data, layer({ subjectSlot: { kind: 'upgrade', index: 0 } }))).toEqual(UPGRADE_S);
  });

  it('a position that does not exist reads none', () => {
    const data = productData({ accessory_box_style: PRODUCT_S, slots });
    expect(accessoryBoxStyleOf(data, layer({ subjectSlot: { kind: 'fixed', index: 5 } }))).toBeNull();
  });

  it('a line layer pointed at a part reads that part\'s style; -1 is the main product', () => {
    const data = lineData({
      accessory_box_style: LINE_S,
      accessories: [],
      parts: [{ accessory_box_style: null }, { accessory_box_style: PART_S }],
      slots,
    });
    expect(accessoryBoxStyleOf(data, layer({ subjectPart: 1 }))).toEqual(PART_S);
    expect(accessoryBoxStyleOf(data, layer({ subjectPart: 0 }))).toBeNull();
    expect(accessoryBoxStyleOf(data, layer({ subjectPart: -1 }))).toEqual(MAIN_S);
  });

  it('is null when nothing names a style, on an old payload, or with no data', () => {
    expect(accessoryBoxStyleOf(productData({ combo: null }), layer())).toBeNull();
    expect(accessoryBoxStyleOf(lineData({ accessories: [], parts: [] }), layer())).toBeNull();
    expect(accessoryBoxStyleOf(null, layer())).toBeNull();
    expect(accessoryBoxStyleOf(undefined, layer())).toBeNull();
    expect(accessoryBoxStyleOf(productData({ accessory_box_style: PRODUCT_S }), undefined)).toEqual(PRODUCT_S);
  });
});

describe('applying a resolved style to a box', () => {
  it('takes the design but keeps the box\'s subject, Reads from and own presetId', () => {
    const own = {
      ...defaultAccessoriesProps(),
      subjectSlot: { kind: 'fixed', index: 0 },
      subjectPart: 2,
      presetId: 'own-preset',
      headerText: 'OLD',
      fill: '#111111',
    } as unknown as AccessoriesLayerProps;
    const resolved = style('override', 'FREE');
    const applied = applyAccessoryDesign(own, resolved.design as never, own.presetId ?? null) as unknown as Record<string, unknown>;
    expect(applied.headerText).toBe('FREE');
    expect(applied.direction).toBe('horizontal');
    expect(applied.subjectSlot).toEqual({ kind: 'fixed', index: 0 });
    expect(applied.subjectPart).toBe(2);
    expect(applied.presetId).toBe('own-preset');
    expect(applied.kind).toBe('accessories');
  });

  it('the design that was applied is not mutated', () => {
    const resolved = style('x', 'FREE');
    const before = JSON.stringify(resolved);
    applyAccessoryDesign(defaultAccessoriesProps(), resolved.design as never, null);
    expect(JSON.stringify(resolved)).toBe(before);
    expect(Object.keys(accessoryDesign(defaultAccessoriesProps()))).not.toContain('presetId');
  });
});
