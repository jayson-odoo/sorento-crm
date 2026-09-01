/**
 * Ruler guide state (D9/D17, S6).
 *
 * Guides are session-only visual aids: dropped from a ruler, dragged to move,
 * dragged back onto the ruler that spawned them to remove. None of it is
 * Konva or React - just the array the editor keeps in memory, and the one
 * geometry question of whether a drag has crossed back over its ruler.
 */

import { describe, expect, it } from 'vitest';

import { guideCrossedIntoRuler, moveGuide, removeGuide, type RulerGuide } from './ruler-guides';

function guide(overrides: Partial<RulerGuide> = {}): RulerGuide {
  return { id: 'g1', orientation: 'vertical', position_mm: 10, ...overrides };
}

describe('moveGuide', () => {
  it('updates only the matching guide', () => {
    const guides = [guide({ id: 'a', position_mm: 5 }), guide({ id: 'b', position_mm: 20 })];
    expect(moveGuide(guides, 'a', 15)).toEqual([
      { id: 'a', orientation: 'vertical', position_mm: 15 },
      { id: 'b', orientation: 'vertical', position_mm: 20 },
    ]);
  });

  it('leaves the array alone when the id is not found', () => {
    const guides = [guide({ id: 'a' })];
    expect(moveGuide(guides, 'missing', 99)).toEqual(guides);
  });
});

describe('removeGuide', () => {
  it('drops the matching guide and keeps the rest', () => {
    const guides = [guide({ id: 'a' }), guide({ id: 'b' })];
    expect(removeGuide(guides, 'a')).toEqual([guide({ id: 'b' })]);
  });

  it('is a no-op for an id that is not there', () => {
    const guides = [guide({ id: 'a' })];
    expect(removeGuide(guides, 'missing')).toEqual(guides);
  });
});

describe('guideCrossedIntoRuler', () => {
  // A vertical guide comes off the TOP ruler (D17), so it goes home when the
  // pointer's stage Y climbs back above the stage's own top edge.
  it('sends a vertical guide home once the pointer rises above the stage', () => {
    expect(guideCrossedIntoRuler('vertical', { x: 40, y: -1 })).toBe(true);
    expect(guideCrossedIntoRuler('vertical', { x: 40, y: 0 })).toBe(false);
    expect(guideCrossedIntoRuler('vertical', { x: 40, y: 50 })).toBe(false);
  });

  // A horizontal guide comes off the LEFT ruler, so X is what matters for it -
  // its own Y wandering around the stage must not delete it.
  it('sends a horizontal guide home once the pointer crosses left of the stage', () => {
    expect(guideCrossedIntoRuler('horizontal', { x: -1, y: 40 })).toBe(true);
    expect(guideCrossedIntoRuler('horizontal', { x: 0, y: 40 })).toBe(false);
    expect(guideCrossedIntoRuler('horizontal', { x: 50, y: -100 })).toBe(false);
  });
});
