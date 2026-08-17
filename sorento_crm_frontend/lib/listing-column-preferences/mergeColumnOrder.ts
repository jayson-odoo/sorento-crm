/**
 * Ensures columnOrder includes every leaf column id (stable DnD + TanStack).
 * Preserves saved order for known ids; a column the saved order has never seen
 * is placed where the code defines it (after its nearest preceding neighbour)
 * rather than at the far right, where a wide grid hides it behind a scroll.
 */
export function mergeColumnOrderWithLeafColumns(
  partialOrder: string[],
  leafColumnIds: string[],
): string[] {
  const allowed = new Set(leafColumnIds);
  const merged = partialOrder.filter((id) => allowed.has(id));
  const seen = new Set(merged);

  leafColumnIds.forEach((id, definitionIndex) => {
    if (seen.has(id)) return;
    seen.add(id);

    let anchor = -1;
    for (let i = definitionIndex - 1; i >= 0 && anchor === -1; i -= 1) {
      anchor = merged.indexOf(leafColumnIds[i]);
    }
    merged.splice(anchor + 1, 0, id);
  });

  return merged;
}
