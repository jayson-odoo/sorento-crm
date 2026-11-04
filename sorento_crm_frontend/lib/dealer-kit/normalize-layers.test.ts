import { describe, expect, it } from 'vitest';

import { normalizeLayers } from './tag-template-types';
import type { TagLayer } from './tag-template-types';

/** A layer as a seeded template or an API call may leave it: no visible, locked, rotation, z. */
const bare = (id: string, extra: Record<string, unknown> = {}) =>
  ({
    id,
    type: 'text',
    x_mm: 1,
    y_mm: 2,
    width_mm: 30,
    height_mm: 8,
    props: { kind: 'text', text: id },
    ...extra,
  }) as unknown as TagLayer;

describe('normalizeLayers: a layer read the way the PDF reads it', () => {
  it('shows a layer with no visible key, and hides only an explicit false', () => {
    const [missing, off, on] = normalizeLayers([bare('a'), bare('b', { visible: false }), bare('c', { visible: true })]);
    expect(missing.visible).toBe(true);
    expect(off.visible).toBe(false);
    expect(on.visible).toBe(true);
  });

  it('fills locked, rotation, z-index, slot binding and text override', () => {
    const [first, second] = normalizeLayers([
      bare('a'),
      bare('b', { rotation: 15, z_index: 7, locked: true, slot_binding: 'code', text_override: 'x' }),
    ]);
    expect(first).toMatchObject({ locked: false, rotation_deg: 0, z_index: 0, slot_binding: null, text_override: null });
    expect(second).toMatchObject({
      locked: true,
      rotation_deg: 15,
      z_index: 7,
      slot_binding: 'code',
      text_override: 'x',
    });
  });

  it('keeps what a saved layer already says and does not touch the input', () => {
    const saved = bare('a', { visible: true, locked: false, rotation_deg: 90, z_index: 3, slot_binding: null, text_override: null });
    const input = [saved];
    const out = normalizeLayers(input);
    expect(out[0]).toEqual(saved);
    expect(input[0]).toBe(saved);
    expect((bare('z') as unknown as Record<string, unknown>).visible).toBeUndefined();
  });
});
