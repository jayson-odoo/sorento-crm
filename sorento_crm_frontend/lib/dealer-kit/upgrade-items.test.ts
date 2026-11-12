/**
 * PRICETAG-UPGRADE-VARIANTS FE test 1: `upgradesOf`.
 *
 * Written test-FIRST. Chosen: `upgradesOf` is exported from `lib/dealer-kit/upgrade-items.ts`
 * (plan S1: branch in `accessoriesOf` without an import cycle). AC-U2, U3, U4, U5.
 */
import { describe, expect, it } from 'vitest';

import type { TagBindingData } from './tag-template-types';
import { upgradesOf } from './upgrade-items';
import { sinkLine } from './test-support/upgrade-variants-fixtures';

describe('upgradesOf', () => {
  it('turns the SRTKS2432 upgrade on offer into one item with its own figures', () => {
    const items = upgradesOf(sinkLine());
    expect(items).toHaveLength(1);
    const [item] = items as unknown as Record<string, unknown>[];
    expect(item).toMatchObject({
      kind: 'upgrade',
      id: 'id-SRTKT71SS',
      code: 'SRTKT71SS',
      name: 'Pull-out shower mixer',
      list_price: 440,
      topup_amount: 150,
      price_with_upgrade: 1099,
    });
  });

  it('takes the lead picture (primary first) and the specs from the slot row', () => {
    const [item] = upgradesOf(sinkLine()) as unknown as {
      image: { attachment_id: string; url: string };
      images: { url: string }[];
      specs: { key: string; raw: string }[];
    }[];
    expect(item.image).toMatchObject({ attachment_id: 'att-SRTKT71SS', url: 'https://cdn/SRTKT71SS.jpg' });
    expect(item.images[0].url).toBe('https://cdn/SRTKT71SS.jpg');
    expect(item.specs).toEqual([expect.objectContaining({ key: 'steel_grade', raw: '304' })]);
  });

  it('reads the same from the designer preview product row', () => {
    const line = sinkLine();
    if (line.kind !== 'line') throw new Error('fixture');
    const { combo, slots, specs, images } = line.line as never as Record<string, unknown>;
    const preview = {
      kind: 'product',
      product: { id: 'host', code: 'SRTKS2432', name: 'Sink', dimensions: '', spec_lines: [], specs, images,
        list_price: 1150, offer_price: 949, promotion_id: null, barcode: null, combo, slots },
    } as unknown as TagBindingData;
    const [item] = upgradesOf(preview) as unknown as Record<string, unknown>[];
    expect(item).toMatchObject({ code: 'SRTKT71SS', list_price: 440, topup_amount: 150, price_with_upgrade: 1099 });
  });

  it('a picked upgrade is part of the package and leaves the list (AC-U4)', () => {
    expect(upgradesOf(sinkLine({ picked: true }))).toEqual([]);
  });

  it('no combo gives nothing (AC-U5)', () => {
    expect(upgradesOf(sinkLine({ combo: false }))).toEqual([]);
    expect(upgradesOf(null)).toEqual([]);
    expect(upgradesOf(undefined)).toEqual([]);
  });

  it('price_with_upgrade is null when the tag has no SP or the upgrade no top-up (AC-U7)', () => {
    const noSp = upgradesOf(sinkLine({ sellPrice: null })) as unknown as Record<string, unknown>[];
    expect(noSp[0].price_with_upgrade).toBeNull();
    const noTopup = upgradesOf(sinkLine({ topup: null })) as unknown as Record<string, unknown>[];
    expect(noTopup[0].topup_amount).toBeNull();
    expect(noTopup[0].price_with_upgrade).toBeNull();
  });

  it('keeps several upgrades in combo order', () => {
    const data = sinkLine();
    if (data.kind !== 'line') throw new Error('fixture');
    const line = data.line as never as { combo: { upgrades: unknown[] }; slots: { upgrades: unknown[] } };
    const second = { ...(line.slots.upgrades[0] as object), product_id: 'id-SRTKT72SS', code: 'SRTKT72SS', list_price: 520 };
    line.combo.upgrades.push({ product_id: 'id-SRTKT72SS', code: 'SRTKT72SS', description: 'Second', topup_amount: 200, picked: false });
    line.slots.upgrades.push({ ...second, topup_amount: 200 });
    const codes = (upgradesOf(data) as unknown as { code: string }[]).map((i) => i.code);
    expect(codes).toEqual(['SRTKT71SS', 'SRTKT72SS']);
  });
});
