/** D: removing any combo part shows "Missing: ..." live, also on a host the server does not guard. */
import { describe, expect, it } from 'vitest';

import { emptyDraftLine, packageWarningFor, partsFromCombo, type DraftLine } from './price-tag-draft-lines';

const combo = {
  combo_id: 'c1',
  name: 'Basin + tap',
  parts: [
    { product_id: 'fx', code: 'SRTWT7449-BL', name: 'Tap', choice_group: null },
    { product_id: 'ta', code: 'SRTKT1', name: 'A', choice_group: 'Colour' },
    { product_id: 'tb', code: 'SRTKT2', name: 'B', choice_group: 'Colour' },
    { product_id: 'up', code: 'SRTUP', name: 'Up', choice_group: null, is_upgrade: true },
  ],
} as never;

const line = (keep: (role: string | null) => boolean, guarded: boolean): DraftLine =>
  ({
    ...emptyDraftLine(),
    line_type: 'product',
    product_id: 'host',
    combo_id: 'c1',
    combos: [combo],
    combos_loaded: true,
    host_guarded: guarded,
    parts: partsFromCombo(combo).filter((p) => keep(p.role)),
  }) as DraftLine;

describe.each([true, false])('packageWarningFor (host guarded: %s)', (guarded) => {
  it('is quiet while every part is there, and the optional upgrade is never a warning', () => {
    expect(packageWarningFor(line((role) => role !== 'Upgrade', guarded))).toBeNull();
  });

  it('names a deleted fixed part by its code', () => {
    expect(packageWarningFor(line((role) => role !== null, guarded))).toBe('Missing: SRTWT7449-BL');
  });

  it('names a deleted choice group', () => {
    expect(packageWarningFor(line((role) => role !== 'Colour', guarded))).toBe('Missing: Colour');
  });
});
