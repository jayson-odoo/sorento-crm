/**
 * Reading a price floor out loud.
 *
 * A floor is a mode plus a number, which nobody can act on. What a person needs is a
 * sentence ("at least 80% of the list price") and, separately, WHERE it came from -
 * because the second is what tells them which policy to go and argue with. The two are
 * kept apart so a surface can show one without the other (the pricing policy list has no
 * inheritance to explain; the product Pricing tab is mostly about inheritance).
 *
 * Pure functions, no formatting library: the server already sends the amounts at the
 * scale it stores them, and re-rounding here would let the two disagree.
 */
import type { EffectiveFloorSource, FloorMode, FloorTargetLevel } from '../types/project.types';

/** Trailing zeros are noise on a percentage: "85.00% of list" reads as false precision. */
function trim(value: string): string {
  const numeric = Number(value);
  return Number.isNaN(numeric) ? value : String(numeric);
}

export function describeFloorRule(rule: { mode: FloorMode; value: string }): string {
  const value = trim(rule.value);
  return rule.mode === 'percent'
    ? `At least ${value}% of the list price`
    : `At least RM ${value}, whatever the list price says`;
}

/**
 * The same sentence, with the resolved ringgit amount when there is one.
 *
 * A percentage read against a CATEGORY has no amount, because a category has no list
 * price. Saying nothing there is correct; inventing a number would not be.
 */
export function describeEffectiveFloor(effective: EffectiveFloorSource): string {
  const sentence = describeFloorRule(effective);
  if (effective.mode === 'percent' && effective.amount) {
    return `${sentence} (RM ${effective.amount})`;
  }
  return sentence;
}

/**
 * Where the floor came from, from the point of view of the thing being edited.
 *
 * "Set on this product" and "Inherited from the Basins category" are different
 * situations with different next actions, and a surface that shows only the number tells
 * the reader neither.
 */
export function describeFloorSource(
  effective: EffectiveFloorSource,
  targetLevel: FloorTargetLevel,
): string {
  if (effective.level === 'product') return 'Set on this product';
  if (effective.level === 'system') return 'Inherited from the company default';
  if (effective.level === 'category' && targetLevel === 'category') {
    return 'Set on this category';
  }
  return `Inherited from the ${effective.source_label} category`;
}
