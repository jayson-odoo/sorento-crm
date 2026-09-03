/**
 * Pure helpers behind the B/I/U/S shortcuts (S2, D4/D10): bold toggles
 * `fontWeight` between 400 and 700 rather than flipping a boolean (there is
 * no separate "bold" flag - weight IS the bold state), while italic,
 * underline and strikethrough are plain booleans applied uniformly across
 * whatever text layers are selected, in one call so the caller can push one
 * history entry for it.
 */
import { describe, expect, it } from 'vitest';

import { toggleBold, toggleTextFlag } from './text-format';
import type { TagLayer } from './tag-template-types';

function textLayer(id: string, overrides: Record<string, unknown> = {}): TagLayer {
  return {
    id,
    type: 'text',
    x_mm: 0,
    y_mm: 0,
    width_mm: 40,
    height_mm: 10,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: {
      kind: 'text',
      text: 'Hello',
      fontFamily: 'DM Sans',
      fontSize: 12,
      fontWeight: 400,
      color: '#000000',
      align: 'left',
      lineHeight: 1.2,
      letterSpacing: 0,
      ...overrides,
    },
  } as TagLayer;
}

describe('toggleBold', () => {
  it('drops a semibold-or-heavier weight to 400 (D10: 600 and up -> 400)', () => {
    expect(toggleBold(600)).toBe(400);
    expect(toggleBold(700)).toBe(400);
    expect(toggleBold(900)).toBe(400);
  });

  it('raises anything below 600 to 700, including 500 (D10)', () => {
    expect(toggleBold(400)).toBe(700);
    expect(toggleBold(500)).toBe(700);
  });
});

describe('toggleTextFlag', () => {
  it('turns a flag on for every targeted layer when not all of them have it', () => {
    const layers = [textLayer('a'), textLayer('b', { italic: true })];
    const next = toggleTextFlag(layers, ['a', 'b'], 'italic');
    expect(next.find((l) => l.id === 'a')?.props).toMatchObject({ italic: true });
    expect(next.find((l) => l.id === 'b')?.props).toMatchObject({ italic: true });
  });

  it('turns a flag off for every targeted layer when all of them already have it', () => {
    const layers = [
      textLayer('a', { underline: true }),
      textLayer('b', { underline: true }),
    ];
    const next = toggleTextFlag(layers, ['a', 'b'], 'underline');
    expect(next.find((l) => l.id === 'a')?.props).toMatchObject({ underline: false });
    expect(next.find((l) => l.id === 'b')?.props).toMatchObject({ underline: false });
  });

  it('reads a layer missing the flag (an old doc) as false, so a mixed selection turns it on', () => {
    const layers = [textLayer('a', { strikethrough: true }), textLayer('b')];
    const next = toggleTextFlag(layers, ['a', 'b'], 'strikethrough');
    expect(next.find((l) => l.id === 'a')?.props).toMatchObject({ strikethrough: true });
    expect(next.find((l) => l.id === 'b')?.props).toMatchObject({ strikethrough: true });
  });

  it('leaves non-text layers and non-targeted layers untouched', () => {
    const shape = {
      id: 'shape-1',
      type: 'shape',
      x_mm: 0,
      y_mm: 0,
      width_mm: 10,
      height_mm: 10,
      rotation_deg: 0,
      z_index: 1,
      locked: false,
      visible: true,
      slot_binding: null,
      text_override: null,
      props: { kind: 'shape', shape: 'rect', fill: '#fff', stroke: '#000', strokeWidth: 1, cornerRadius: 0 },
    } as TagLayer;
    const untouched = textLayer('c');
    const layers = [textLayer('a'), shape, untouched];
    const next = toggleTextFlag(layers, ['a'], 'italic');
    expect(next.find((l) => l.id === 'shape-1')).toBe(shape);
    expect(next.find((l) => l.id === 'c')).toBe(untouched);
    expect(next.find((l) => l.id === 'a')?.props).toMatchObject({ italic: true });
  });

  it('ignores an id that is not a text layer or does not exist', () => {
    const layers = [textLayer('a')];
    const next = toggleTextFlag(layers, ['a', 'missing'], 'italic');
    expect(next.find((l) => l.id === 'a')?.props).toMatchObject({ italic: true });
    expect(next).toHaveLength(1);
  });
});
