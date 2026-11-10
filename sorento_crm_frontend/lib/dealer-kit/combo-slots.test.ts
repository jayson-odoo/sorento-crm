/**
 * PRICETAG-COMBO-RENDER K4 (FE half): `lib/dealer-kit/combo-slots.ts`.
 *
 * Written test-FIRST; the module does not exist (the whole file is red on the unresolved import). The words match the backend's `fit_reason` exactly.
 *
 * Decisions where the plan is open:
 * - `needsText(needs, shape)` words: "Needs 3 from Kitchen tap, upgrade" (groups, then fixed
 *   parts, then upgrades, comma separated, each only when needed); nothing needed is "Needs the
 *   main product only"; with a null shape a group is called "choice group N".
 * - `groupIndexOf(role, shape)` is the 0-based group index, -1 when the shape has no such role.
 */
import { describe, expect, it } from 'vitest';

type Part = {
  product_id: string;
  code: string;
  name: string;
  choice_group: string | null;
  is_upgrade?: boolean;
  topup_amount?: number | null;
  is_discontinued?: boolean;
};
type Needs = { fixed: number; groups: number[]; upgrades: number };

import * as comboSlots from './combo-slots';

type Shape = { fixed: number; groups: { role: string; size: number }[]; upgrades: number };
const api = comboSlots as unknown as {
  comboShape: (parts: Part[]) => Shape;
  fitReason: (needs: Needs, shape: Shape) => string | null;
  needsText: (needs: Needs, shape: Shape | null) => string;
  groupIndexOf: (role: string, shape: Shape) => number;
};
async function mod() {
  return api;
}

const p = (code: string, group: string | null = null, extra: Partial<Part> = {}): Part => ({
  product_id: `id-${code}`,
  code,
  name: code,
  choice_group: group,
  ...extra,
});

const S1_PARTS = [
  ...['SRTKT1862SS', 'SRTKT1863SS', 'SRTKT1871SS', 'SRTKT1880SS', 'SRTKT1892SS'].map((c) => p(c, 'Kitchen tap')),
  p('SRTKT71SS', null, { is_upgrade: true, topup_amount: 150 }),
];
const S2_PARTS = [p('SRTWT7449-BL')];
const S3_PARTS = [p('SRTWT7449-BL', 'Tap colour'), p('SRTWT7449-RG', 'Tap colour')];
const S4_PARTS = [p('SRTMCB8083-BL'), p('SRTWT6203-GM')];

describe('comboShape', () => {
  it('S1 and S5: one group of five and one upgrade', async () => {
    expect((await mod()).comboShape(S1_PARTS)).toEqual({
      fixed: 0,
      groups: [{ role: 'Kitchen tap', size: 5 }],
      upgrades: 1,
    });
  });
  it('S2: one fixed part', async () => {
    expect((await mod()).comboShape(S2_PARTS)).toEqual({ fixed: 1, groups: [], upgrades: 0 });
  });
  it('S3: one group of two', async () => {
    expect((await mod()).comboShape(S3_PARTS)).toEqual({
      fixed: 0,
      groups: [{ role: 'Tap colour', size: 2 }],
      upgrades: 0,
    });
  });
  it('S4: two fixed parts', async () => {
    expect((await mod()).comboShape(S4_PARTS)).toEqual({ fixed: 2, groups: [], upgrades: 0 });
  });
  it('groups come in first-appearance order and a grouped upgrade is an upgrade only', async () => {
    const parts = [
      p('A1', 'Second'),
      p('B1', 'First'),
      p('A2', 'Second'),
      p('U1', 'Second', { is_upgrade: true }),
    ];
    // COMBO-SETTINGS-UX owner round 1: "First" has one part, so it is a fixed part, not a group.
    expect((await mod()).comboShape(parts)).toEqual({
      fixed: 1,
      groups: [{ role: 'Second', size: 2 }],
      upgrades: 1,
    });
  });
});

describe('fitReason', () => {
  it('S1: three of five fits with the upgrade; six does not', async () => {
    const m = await mod();
    const shape = m.comboShape(S1_PARTS);
    expect(m.fitReason({ fixed: 0, groups: [3], upgrades: 1 }, shape)).toBeNull();
    expect(m.fitReason({ fixed: 0, groups: [6], upgrades: 0 }, shape)).toBe(
      'Needs 6 from Kitchen tap; this combo has 5',
    );
  });
  it('S2: one fixed fits, two does not, a group does not exist', async () => {
    const m = await mod();
    const shape = m.comboShape(S2_PARTS);
    expect(m.fitReason({ fixed: 1, groups: [], upgrades: 0 }, shape)).toBeNull();
    expect(m.fitReason({ fixed: 2, groups: [], upgrades: 0 }, shape)).toBe(
      'Needs 2 fixed parts; this combo has 1',
    );
    expect(m.fitReason({ fixed: 1, groups: [1], upgrades: 0 }, shape)).toBe(
      'Needs a choice group; this combo has none',
    );
  });
  it('S3: needs 3 of 2 names the shortfall; 1 and 2 fit', async () => {
    const m = await mod();
    const shape = m.comboShape(S3_PARTS);
    expect(m.fitReason({ fixed: 0, groups: [3], upgrades: 0 }, shape)).toBe(
      'Needs 3 from Tap colour; this combo has 2',
    );
    expect(m.fitReason({ fixed: 0, groups: [1], upgrades: 0 }, shape)).toBeNull();
    expect(m.fitReason({ fixed: 0, groups: [2], upgrades: 0 }, shape)).toBeNull();
    expect(m.fitReason({ fixed: 0, groups: [0, 1], upgrades: 0 }, shape)).toBe(
      'Needs choice group 2; this combo has 1',
    );
  });
  it('S4: two fixed fits, three does not', async () => {
    const m = await mod();
    const shape = m.comboShape(S4_PARTS);
    expect(m.fitReason({ fixed: 2, groups: [], upgrades: 0 }, shape)).toBeNull();
    expect(m.fitReason({ fixed: 3, groups: [], upgrades: 0 }, shape)).toBe(
      'Needs 3 fixed parts; this combo has 2',
    );
  });
  it('M1: a template must print every fixed part the combo has', async () => {
    const m = await mod();
    const shape = m.comboShape(S4_PARTS);
    expect(m.fitReason({ fixed: 1, groups: [], upgrades: 0 }, shape)).toBe(
      "Prints 1 of this combo's 2 fixed parts",
    );
  });
  it('HOTFIX: a plain template (no position field) fits every combo, fixed parts too', async () => {
    const m = await mod();
    for (const parts of [S1_PARTS, S3_PARTS, S4_PARTS]) {
      expect(m.fitReason({ fixed: 0, groups: [], upgrades: 0 }, m.comboShape(parts))).toBeNull();
      expect(m.fitReason({ fixed: 0, groups: [0], upgrades: 0 }, m.comboShape(parts))).toBeNull();
    }
  });
  it('HOTFIX: a partial template that reads some position is still refused', async () => {
    const m = await mod();
    expect(m.fitReason({ fixed: 0, groups: [], upgrades: 1 }, m.comboShape(S4_PARTS))).toBe(
      "Prints 0 of this combo's 2 fixed parts",
    );
  });
  it('R2: a picks template on a combo with fixed parts and no group names the group first', async () => {
    const m = await mod();
    expect(m.fitReason({ fixed: 0, groups: [2], upgrades: 0 }, m.comboShape(S4_PARTS))).toBe(
      'Needs a choice group; this combo has none',
    );
  });
  it('S5: the upgrade need fits one upgrade, two do not, none on a combo without', async () => {
    const m = await mod();
    expect(m.fitReason({ fixed: 0, groups: [1], upgrades: 1 }, m.comboShape(S1_PARTS))).toBeNull();
    expect(m.fitReason({ fixed: 0, groups: [], upgrades: 2 }, m.comboShape(S1_PARTS))).toBe(
      'Needs 2 upgrades; this combo has 1',
    );
    expect(m.fitReason({ fixed: 2, groups: [], upgrades: 1 }, m.comboShape(S4_PARTS))).toBe(
      'Needs 1 upgrade; this combo has 0',
    );
  });
  it('a template that needs nothing fits every shape without a fixed part', async () => {
    const m = await mod();
    for (const parts of [S1_PARTS, S3_PARTS]) {
      expect(m.fitReason({ fixed: 0, groups: [], upgrades: 0 }, m.comboShape(parts))).toBeNull();
    }
  });
});

describe('needsText', () => {
  it('S1: names the group in the combo words and the upgrade', async () => {
    const m = await mod();
    expect(m.needsText({ fixed: 0, groups: [3], upgrades: 1 }, m.comboShape(S1_PARTS))).toBe(
      'Needs 3 from Kitchen tap, upgrade',
    );
  });
  it('S3: a group alone', async () => {
    const m = await mod();
    expect(m.needsText({ fixed: 0, groups: [2], upgrades: 0 }, m.comboShape(S3_PARTS))).toBe(
      'Needs 2 from Tap colour',
    );
  });
  it('S2 and S4: fixed parts', async () => {
    const m = await mod();
    expect(m.needsText({ fixed: 1, groups: [], upgrades: 0 }, m.comboShape(S2_PARTS))).toMatch(/Needs 1 fixed part/);
    expect(m.needsText({ fixed: 2, groups: [], upgrades: 0 }, m.comboShape(S4_PARTS))).toMatch(/Needs 2 fixed parts/);
  });
  it('nothing needed is the main product only', async () => {
    const m = await mod();
    expect(m.needsText({ fixed: 0, groups: [], upgrades: 0 }, m.comboShape(S1_PARTS))).toBe(
      'Needs the main product only',
    );
    expect(m.needsText({ fixed: 0, groups: [0, 0], upgrades: 0 }, null)).toBe('Needs the main product only');
  });
  it('without a combo the group is called by number', async () => {
    const m = await mod();
    expect(m.needsText({ fixed: 0, groups: [3], upgrades: 1 }, null)).toBe(
      'Needs 3 from choice group 1, upgrade',
    );
  });
});

describe('groupIndexOf', () => {
  it('is the 0-based group index, -1 for an unknown role', async () => {
    const m = await mod();
    const shape = m.comboShape([p('A', 'Second'), p('B', 'First'), p('A2', 'Second'), p('B2', 'First')]);
    expect(m.groupIndexOf('Second', shape)).toBe(0);
    expect(m.groupIndexOf('First', shape)).toBe(1);
    expect(m.groupIndexOf('Upgrade', shape)).toBe(-1);
  });
});

describe('comboShape, one-part groups (COMBO-SETTINGS-UX owner round 1)', () => {
  it('counts a group with one part as a fixed part; a choice is 2+ parts', async () => {
    expect(
      (await mod()).comboShape([
        { choice_group: null },
        { choice_group: 'Test' },
        { choice_group: 'TAP' },
        { choice_group: 'TAP' },
        { choice_group: 'Kitchen tap' },
        { choice_group: 'Kitchen tap', is_upgrade: true },
      ]),
    ).toEqual({ fixed: 3, groups: [{ role: 'TAP', size: 2 }], upgrades: 1 });
  });
});
