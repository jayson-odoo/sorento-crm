/**
 * Session-only ruler guides (D9/D17, S6).
 *
 * A guide is dropped by clicking or dragging out from a ruler - the TOP one
 * spawns a VERTICAL guide (it measures X), the LEFT one a HORIZONTAL one (it
 * measures Y) - then dragged to move, or dragged back onto the ruler that
 * spawned it to remove (Figma/Word convention). None of this ever touches the
 * document: guides live in React state only, never saved, never exported.
 */

export interface RulerGuide {
  id: string;
  orientation: 'vertical' | 'horizontal';
  position_mm: number;
}

let guideIdSeq = 0;
export function newGuideId(): string {
  guideIdSeq += 1;
  return `guide-${Date.now()}-${guideIdSeq}`;
}

/** Reposition one guide, leaving the rest (and the array, if the id misses) alone. */
export function moveGuide(guides: RulerGuide[], id: string, position_mm: number): RulerGuide[] {
  return guides.map((g) => (g.id === id ? { ...g, position_mm } : g));
}

/** Drop one guide. A no-op if the id is not present. */
export function removeGuide(guides: RulerGuide[], id: string): RulerGuide[] {
  return guides.filter((g) => g.id !== id);
}

/**
 * Whether a guide being dragged has crossed back over the ruler that spawned
 * it, meaning the drag should delete it rather than relocate it.
 *
 * `pointer` is in STAGE pixels - the same space `stageToMm` reads - which is
 * why this can go negative at all: the ruler strips sit just outside the
 * Stage's own top-left corner, so a pointer that wanders back above (for a
 * vertical guide's top ruler) or left of (for a horizontal guide's left
 * ruler) that origin has physically re-entered ruler territory.
 */
export function guideCrossedIntoRuler(
  orientation: RulerGuide['orientation'],
  pointer: { x: number; y: number },
): boolean {
  return orientation === 'vertical' ? pointer.y < 0 : pointer.x < 0;
}
