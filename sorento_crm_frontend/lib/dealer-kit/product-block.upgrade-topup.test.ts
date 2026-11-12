/**
 * PRICETAG-UPGRADE-VARIANTS FE test 5 (AC-U8): the free text slots `upgrade_topup` and
 * `sell_price_with_upgrade` on an "Upgrade N" position print the same words as the card.
 *
 * Written test-FIRST. `TextLayerProps.prefix` is used only by these two slots.
 */
import { describe, expect, it } from 'vitest';

import { resolveSlotText } from './product-block';
import { sinkLine } from './test-support/upgrade-variants-fixtures';
import type { TagBindingData } from './tag-template-types';

const layer = (slot: string, subjectSlot: unknown, prefix?: string, extra: Record<string, unknown> = {}) =>
  ({
    slot_binding: slot,
    props: { kind: 'text', ...(subjectSlot ? { subjectSlot } : {}), ...(prefix ? { prefix } : {}), ...extra },
  }) as never;

const UP1 = { kind: 'upgrade', index: 0 };

describe('upgrade_topup', () => {
  it('prints prefix + top-up on Upgrade 1', () => {
    expect(resolveSlotText(layer('upgrade_topup', UP1, 'TOPUP '), sinkLine())).toBe('TOPUP RM 150');
  });

  it('prints the bare figure without a prefix', () => {
    expect(resolveSlotText(layer('upgrade_topup', UP1), sinkLine())).toBe('RM 150');
  });

  it('follows showCurrency like every price text', () => {
    expect(resolveSlotText(layer('upgrade_topup', UP1, 'TOPUP ', { showCurrency: false }), sinkLine())).toBe('TOPUP 150');
  });

  it('is empty once the upgrade is picked', () => {
    expect(resolveSlotText(layer('upgrade_topup', UP1, 'TOPUP '), sinkLine({ picked: true }))).toBe('');
  });

  it('is empty when the upgrade has no top-up', () => {
    expect(resolveSlotText(layer('upgrade_topup', UP1, 'TOPUP '), sinkLine({ topup: null }))).toBe('');
  });

  it('is empty when the layer is not on an upgrade position', () => {
    expect(resolveSlotText(layer('upgrade_topup', undefined, 'TOPUP '), sinkLine())).toBe('');
    expect(resolveSlotText(layer('upgrade_topup', { kind: 'main' }, 'TOPUP '), sinkLine())).toBe('');
    expect(resolveSlotText(layer('upgrade_topup', { kind: 'fixed', index: 0 }, 'TOPUP '), sinkLine())).toBe('');
  });

  it('is empty on Upgrade 2 when the combo has one upgrade', () => {
    expect(resolveSlotText(layer('upgrade_topup', { kind: 'upgrade', index: 1 }, 'TOPUP '), sinkLine())).toBe('');
  });

  it('is empty on a payload with no slots (older pin)', () => {
    const data = sinkLine();
    if (data.kind === 'line') delete (data.line as never as Record<string, unknown>).slots;
    expect(resolveSlotText(layer('upgrade_topup', UP1, 'TOPUP '), data as TagBindingData)).toBe('');
  });
});

describe('sell_price_with_upgrade', () => {
  it('prints the tag SP plus the top-up', () => {
    expect(resolveSlotText(layer('sell_price_with_upgrade', UP1, 'SP with upgrade '), sinkLine())).toBe(
      'SP with upgrade RM 1,099',
    );
  });

  it('is empty when the tag has no SP to add to', () => {
    expect(resolveSlotText(layer('sell_price_with_upgrade', UP1, 'SP with upgrade '), sinkLine({ sellPrice: null }))).toBe('');
  });

  it('is empty once picked, with no top-up, or off an upgrade position', () => {
    expect(resolveSlotText(layer('sell_price_with_upgrade', UP1, 'SP with upgrade '), sinkLine({ picked: true }))).toBe('');
    expect(resolveSlotText(layer('sell_price_with_upgrade', UP1, 'SP with upgrade '), sinkLine({ topup: null }))).toBe('');
    expect(resolveSlotText(layer('sell_price_with_upgrade', undefined, 'SP with upgrade '), sinkLine())).toBe('');
  });
});

describe('same words as the card', () => {
  it('the slot and the card element share one formatter', async () => {
    const { cardFieldValue } = await import('./accessory-card');
    const item = { kind: 'upgrade', id: 'u', name: 'x', spec: null, image: null, topup_amount: 150 };
    const slot = resolveSlotText(layer('upgrade_topup', UP1), sinkLine());
    expect(slot).toBe(cardFieldValue(item as never, 'topup' as never));
  });
});
