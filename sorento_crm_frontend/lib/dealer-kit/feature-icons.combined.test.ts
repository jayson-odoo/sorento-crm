/**
 * SPEC-ICON-COMBINED F1, F2: an icon set on one spec value may carry an AND list of conditions on
 * OTHER spec keys. Plan: documentation/plans/dealer-kit/PLAN-spec-icon-combined-09nov.md.
 *
 * Union (Q1): a conditioned icon never suppresses another icon. Any missing condition value (Q4)
 * and the icon does not print. Variants match per member, never across members.
 */
import { describe, expect, it } from 'vitest';

import { featureIconsFor, variantFeatureIcons, type FeatureIcon } from './feature-icons';

const spec = (key: string, raw?: string) => ({ key, raw });

const S_TRAP: FeatureIcon = { id: 's', name: 'S trap', spec_key: 'trap_type', values: ['s_trap'] };
const P_TRAP: FeatureIcon = { id: 'p', name: 'P trap', spec_key: 'trap_type', values: ['p_trap'] };
const S_150: FeatureIcon = {
  id: 's150',
  name: 'S trap 150mm',
  spec_key: 'trap_length',
  values: ['150'],
  conditions: [{ spec_key: 'trap_type', value: 's_trap' }],
};
const ICONS: FeatureIcon[] = [S_TRAP, P_TRAP, S_150];
const ids = (list: { id: string }[]) => list.map((i) => i.id);

describe('F1 featureIconsFor with conditions', () => {
  it('F1 S trap at 150mm prints both the single icon and the combined one (union)', () => {
    const out = featureIconsFor([spec('trap_type', 's_trap'), spec('trap_length', '150')], ICONS);
    expect(ids(out)).toEqual(['s', 's150']);
  });

  it('F1 S trap at 200mm prints only S trap', () => {
    const out = featureIconsFor([spec('trap_type', 's_trap'), spec('trap_length', '200')], ICONS);
    expect(ids(out)).toEqual(['s']);
  });

  it('F1 P trap at 150mm does not print the S trap 150mm icon', () => {
    const out = featureIconsFor([spec('trap_type', 'p_trap'), spec('trap_length', '150')], ICONS);
    expect(ids(out)).toEqual(['p']);
  });

  it('F1 S trap with no length does not print the combined icon, and takes no space', () => {
    const out = featureIconsFor([spec('trap_type', 's_trap')], ICONS);
    expect(ids(out)).toEqual(['s']);
  });

  it('F1 a condition partner with no raw value counts as missing', () => {
    const out = featureIconsFor([spec('trap_type'), spec('trap_length', '150')], ICONS);
    expect(ids(out)).toEqual([]);
  });

  it('F1 the host value alone, without the partner row at all, does not print it', () => {
    expect(ids(featureIconsFor([spec('trap_length', '150')], [S_150]))).toEqual([]);
  });

  it('F1 an icon with empty or absent conditions behaves exactly as before', () => {
    const plain: FeatureIcon = { ...S_TRAP, conditions: [] };
    expect(ids(featureIconsFor([spec('trap_type', 's_trap')], [plain, P_TRAP]))).toEqual(['s']);
    expect(ids(featureIconsFor([spec('trap_type', 's_trap')], [S_TRAP]))).toEqual(['s']);
  });

  it('F1 a 3-spec AND needs all three partners to match', () => {
    const triple: FeatureIcon = {
      id: 't3',
      name: 'S trap 150mm SUS',
      spec_key: 'trap_length',
      values: ['150'],
      conditions: [
        { spec_key: 'trap_type', value: 's_trap' },
        { spec_key: 'steel_grade', value: '304' },
      ],
    };
    const all = [spec('trap_length', '150'), spec('trap_type', 's_trap'), spec('steel_grade', '304')];
    expect(ids(featureIconsFor(all, [triple]))).toEqual(['t3']);
    expect(ids(featureIconsFor(all.filter((s) => s.key !== 'steel_grade'), [triple]))).toEqual([]);
    expect(ids(featureIconsFor(all.filter((s) => s.key !== 'trap_type'), [triple]))).toEqual([]);
    expect(ids(featureIconsFor([...all.slice(0, 2), spec('steel_grade', '316')], [triple]))).toEqual([]);
  });

  it('F1 keeps the input order and dedupes by asset id (first matching slot wins)', () => {
    const early: FeatureIcon = { ...S_150, id: 'dup' };
    const late: FeatureIcon = { ...S_150, id: 'dup', spec_key: 'trap_length', values: ['150', '200'] };
    const out = featureIconsFor(
      [spec('trap_type', 's_trap'), spec('trap_length', '150')],
      [early, S_TRAP, late],
    );
    expect(ids(out)).toEqual(['dup', 's']);
  });
});

describe('F2 variantFeatureIcons with conditions', () => {
  it('F2 matches conditions per member, never across members', () => {
    const memberA = [spec('trap_type', 's_trap'), spec('trap_length', '200')];
    const memberB = [spec('trap_type', 'p_trap'), spec('trap_length', '150')];
    const out = variantFeatureIcons([memberA, memberB], ICONS);
    expect(ids(out)).toEqual(['s', 'p']);
    expect(ids(out)).not.toContain('s150');
  });

  it('F2 a member that satisfies the whole rule contributes the combined icon, in input order', () => {
    const memberA = [spec('trap_type', 's_trap'), spec('trap_length', '150')];
    const memberB = [spec('trap_type', 'p_trap'), spec('trap_length', '200')];
    expect(ids(variantFeatureIcons([memberA, memberB], ICONS))).toEqual(['s', 'p', 's150']);
  });
});
