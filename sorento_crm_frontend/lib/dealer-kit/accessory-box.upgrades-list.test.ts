/**
 * PRICETAG-UPGRADE-VARIANTS FE test 2: `accessoriesOf` with `list: 'upgrades'` reads the combo's
 * upgrades on offer (via `upgradesOf` in `./upgrade-items`); without `list` it is unchanged.
 * Written test-FIRST. AC-U1, U2, U4, U5.
 */
import { describe, expect, it } from 'vitest';

import { accessoriesOf } from './accessory-box';
import { defaultAccessoriesProps } from './tag-template-types';
import { sinkLine } from './test-support/upgrade-variants-fixtures';

const upgradesLayer = (extra: Record<string, unknown> = {}) =>
  ({ props: { ...defaultAccessoriesProps(), list: 'upgrades', ...extra } }) as never;
const codes = (items: unknown) => (items as { code?: string }[]).map((i) => i.code);

describe('accessoriesOf with list: upgrades', () => {
  it('returns upgradesOf for an Upgrades box (AC-U2)', () => {
    const data = sinkLine();
    expect(codes(accessoriesOf(data, upgradesLayer()))).toEqual(['SRTKT71SS']);
    expect(accessoriesOf(data, upgradesLayer())[0]).toMatchObject({ kind: 'upgrade', topup_amount: 150 });
  });

  it('ignores subjectSlot and subjectPart on an Upgrades box', () => {
    const data = sinkLine();
    const layer = upgradesLayer({ subjectSlot: { kind: 'fixed', index: 0 }, subjectPart: 0 });
    expect(codes(accessoriesOf(data, layer))).toEqual(['SRTKT71SS']);
  });

  it('a box with list free, or no list at all, keeps today behaviour', () => {
    const data = sinkLine();
    if (data.kind !== 'line') throw new Error('fixture');
    (data.line as never as { accessories: unknown[] }).accessories = [{ id: 'a1', name: 'DRAINER', spec: null, image: null }];
    const plain = { props: defaultAccessoriesProps() } as never;
    const free = { props: { ...defaultAccessoriesProps(), list: 'free' } } as never;
    expect(accessoriesOf(data, plain)).toEqual([expect.objectContaining({ id: 'a1' })]);
    expect(accessoriesOf(data, free)).toEqual([expect.objectContaining({ id: 'a1' })]);
  });

  it('prints nothing when the combo has no upgrades left', () => {
    expect(accessoriesOf(sinkLine({ picked: true }), upgradesLayer())).toEqual([]);
    expect(accessoriesOf(sinkLine({ combo: false }), upgradesLayer())).toEqual([]);
  });
});
