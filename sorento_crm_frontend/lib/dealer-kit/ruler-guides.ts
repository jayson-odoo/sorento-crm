/**
 * Session-only ruler guides (D9/D17, S6; D21, S8).
 *
 * A guide is dropped by clicking or dragging out from a ruler - the TOP one
 * spawns a VERTICAL guide (it measures X), the LEFT one a HORIZONTAL one (it
 * measures Y) - then dragged to move, or dragged back onto the ruler that
 * spawned it to remove (Figma/Word convention). None of this ever touches the
 * document: guides live in React state only, never saved, never exported.
 *
 * D21 (round 3): at most ONE guide per axis. A click on a ruler with that
 * axis's guide already placed MOVES it rather than adding a second one -
 * `placeOrMoveGuide` is the one function both the click and the drag-spawn
 * gesture go through, so there is exactly one place that rule can drift from.
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

/**
 * A ruler click, single-guide-per-axis (D21, AC-S8-1).
 *
 * No guide on this axis yet: place one, using `id` as its identity. One
 * already there: MOVE that same guide - its id, not `id` - so a second click
 * on the same ruler never produces a second guide. The caller decides `id`
 * (a fresh one, in case this call turns out to be a placement) so it can hand
 * the SAME id to whatever starts tracking the ensuing drag.
 */
export function placeOrMoveGuide(
  guides: RulerGuide[],
  orientation: RulerGuide['orientation'],
  id: string,
  position_mm: number,
): RulerGuide[] {
  const existing = guides.find((g) => g.orientation === orientation);
  if (existing) return moveGuide(guides, existing.id, position_mm);
  return [...guides, { id, orientation, position_mm }];
}

/** The axis's one guide, if it has been placed - what the ruler's own x chip reads. */
export function guideForAxis(
  guides: RulerGuide[],
  orientation: RulerGuide['orientation'],
): RulerGuide | null {
  return guides.find((g) => g.orientation === orientation) ?? null;
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
