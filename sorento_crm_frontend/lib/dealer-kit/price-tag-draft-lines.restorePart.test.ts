/** P2: Add part first lists the combo's own missing rows; one can come back alone, at its place. */
import { describe, expect, it } from 'vitest';

import {
  emptyDraftLine,
  insertComboRow,
  missingComboRows,
  partsFromCombo,
  type DraftLine,
} from './price-tag-draft-lines';

const combo = {
  combo_id: 'c1',
  name: 'Sink combo',
  parts: [
    { product_id: 'fx', code: 'SRTFIX', name: 'Fixed', choice_group: null },
    { product_id: 'ta', code: 'SRTKT1', name: 'Tap A', choice_group: 'Kitchen tap' },
    { product_id: 'tb', code: 'SRTKT2', name: 'Tap B', choice_group: 'Kitchen tap' },
    { product_id: 'up', code: 'SRTKT71SS', name: 'Upgrade', choice_group: null, is_upgrade: true },
  ],
} as never;

function lineWith(keep: (role: string | null, code: string) => boolean): DraftLine {
  return {
    ...emptyDraftLine(),
    combo_id: 'c1',
    combos: [combo],
    parts: partsFromCombo(combo).filter((p) => keep(p.role, p.code)),
  } as DraftLine;
}

describe('missingComboRows', () => {
  it('lists nothing while the line holds every combo row', () => {
    expect(missingComboRows(lineWith(() => true))).toEqual([]);
  });

  it('names a missing group, the upgrade and a missing fixed part by code, in combo order', () => {
    const rows = missingComboRows(lineWith(() => false));
    expect(rows.map((r) => r.label)).toEqual(['SRTFIX', 'Kitchen tap', 'Upgrade']);
  });

  it('lists only the upgrade after it alone was deleted', () => {
    const rows = missingComboRows(lineWith((role) => role !== 'Upgrade'));
    expect(rows.map((r) => r.label)).toEqual(['Upgrade']);
    expect(rows[0].row.role).toBe('Upgrade');
    expect(rows[0].row.candidates.map((c) => c.code)).toEqual(['SRTKT71SS']);
  });
});

describe('insertComboRow', () => {
  it('puts the row back at its combo position, ahead of an a la carte part', () => {
    const line = lineWith((role) => role !== null || false);
    const extra = { key: 'x', product_id: 'zz', code: 'ZZ', name: 'Extra', role: null, candidates: [] };
    const parts = [...line.parts, extra] as never[];
    const fixed = missingComboRows({ ...line, parts } as DraftLine).find((r) => r.label === 'SRTFIX')!;
    const next = insertComboRow({ ...line, parts } as DraftLine, fixed.id);
    expect(next.map((p) => p.code || p.role)).toEqual(['SRTFIX', 'Kitchen tap', 'Upgrade', 'ZZ']);
  });

  it('restores the upgrade alone, leaving the Kitchen tap row untouched', () => {
    const line = lineWith((role) => role !== 'Upgrade');
    const tap = line.parts.find((p) => p.role === 'Kitchen tap')!;
    const upgrade = missingComboRows(line)[0];
    const next = insertComboRow(line, upgrade.id);
    expect(next.map((p) => p.role ?? p.code)).toEqual(['SRTFIX', 'Kitchen tap', 'Upgrade']);
    expect(next.find((p) => p.role === 'Kitchen tap')).toBe(tap);
  });
});
