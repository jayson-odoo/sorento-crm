/**
 * The SPO detail route, spelled once.
 *
 * `/procurement-management/spo-allocations/[spoNumber]` reads `spoNumber` off the URL, and
 * an SPO number can carry a literal `/` (`SPO-2026/08-0061`), which a Next.js dynamic
 * segment must receive as ONE encoded path piece - `PackingListLinesTab.tsx`,
 * `SPOAllocationsList.tsx` and `SpoAllocationCell.tsx` each built this same string before
 * this existed; use this instead of a fourth copy.
 */
export function spoDetailHref(spoNumber: string): string {
  return `/procurement-management/spo-allocations/${encodeURIComponent(spoNumber)}`;
}

/**
 * `SPO 202607-S0105` -> `202607-S0105`; `SPO-2026/08-0085` -> itself, unchanged.
 *
 * The engine's own sentence (`front_planning_engine.spo_reason` /
 * `stock_debt_service._spo_ref`) prepends the word "SPO " only to a raw number that does not
 * already carry it, so this is the exact inverse: a label with "SPO" followed by whitespace
 * had the word ADDED and the rest is the real number this route expects; anything else - a
 * bare `202607-S0105` or a number already written `SPO-...` - already IS the real number.
 */
export function spoNumberFromLabel(label: string): string {
  const match = /^SPO\s+(.+)$/.exec(label.trim());
  return match ? match[1] : label.trim();
}
