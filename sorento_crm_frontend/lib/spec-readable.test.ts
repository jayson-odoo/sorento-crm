/**
 * AC-E.1 - `readableValue` / `readableEntry` take a value's display labels (#423,
 * folded into the spec workbench redesign).
 */
import { describe, expect, it } from 'vitest';
import { readable, readableEntry, readableValue, valueLabelsByKey } from './spec-readable';

describe('readableValue with labels', () => {
  it('reads a labelled value through the label', () => {
    expect(readableValue('pp', undefined, { pp: 'PP' })).toBe('PP');
  });

  it('falls back to the automatic title-case reading with no label', () => {
    expect(readableValue('pp')).toBe('Pp');
  });

  it('falls back when the labels dict has no entry for this value', () => {
    expect(readableValue('pp', undefined, { chrome: 'Chrome finish' })).toBe('Pp');
  });

  it('appends the unit after a label the same way as the automatic reading', () => {
    expect(readableValue('pp', 'mm', { pp: 'PP' })).toBe('PP mm');
  });

  it('maps a list element-wise, each through its own label', () => {
    expect(
      readableValue(['pp', 'abs'], undefined, { pp: 'PP', abs: 'ABS' }),
    ).toBe('PP, ABS');
  });

  it('leaves numbers and booleans unaffected by labels', () => {
    expect(readableValue(770, 'mm', { '770': 'Seven seventy' })).toBe('770 mm');
    expect(readableValue(true, undefined, { true: 'On' })).toBe('Yes');
  });
});

describe('readableEntry with labels', () => {
  it('reads a stored entry through the label', () => {
    expect(readableEntry({ value: 'pp' }, { pp: 'PP' })).toBe('PP');
  });

  it('still reads a bare scalar through the label', () => {
    expect(readableEntry('pp', { pp: 'PP' })).toBe('PP');
  });
});

describe('valueLabelsByKey', () => {
  it('keys a registry array by spec_key, dropping keys with no labels', () => {
    const registry: { spec_key: string; value_labels?: Record<string, string> }[] = [
      { spec_key: 'seat_material', value_labels: { pp: 'PP' } },
      { spec_key: 'finish', value_labels: {} },
      { spec_key: 'class' },
    ];
    expect(valueLabelsByKey(registry)).toEqual({ seat_material: { pp: 'PP' } });
  });

  it('answers an empty map for an undefined registry', () => {
    expect(valueLabelsByKey(undefined)).toEqual({});
  });
});

describe('readable (unlabelled - unchanged)', () => {
  it('still turns a raw key into words', () => {
    expect(readable('dim_height')).toBe('Height');
  });
});
