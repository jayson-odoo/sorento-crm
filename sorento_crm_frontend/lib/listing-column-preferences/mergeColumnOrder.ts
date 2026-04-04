/**
 * Ensures columnOrder includes every leaf column id (stable DnD + TanStack).
 * Preserves saved order for known ids; appends any new columns in definition order.
 */
export function mergeColumnOrderWithLeafColumns(
  partialOrder: string[],
  leafColumnIds: string[],
): string[] {
  const allowed = new Set(leafColumnIds);
  const base = partialOrder.filter((id) => allowed.has(id));
  const seen = new Set(base);
  const missing = leafColumnIds.filter((id) => !seen.has(id));
  return [...base, ...missing];
}
