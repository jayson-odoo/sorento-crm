/**
 * How far a sales order has been PLANNED, in one chip.
 *
 * The owner's question off SO421404 (14 September 2026): "how do I know if the order is fully
 * planned from the list itself?" The list already names the order inquiries raised against an
 * order, which answers what purchasing was told - it does not answer whether anybody decided
 * where the stock comes from. A completed order can read Completed, three of three delivered,
 * and never have been planned at all.
 *
 * TWO COUNTS OFF THE SERVER, never re-derived here. `plannable_lines` is how many lines the
 * fulfilment board would admit and `planned_lines` how many of those are settled - both
 * counted by the board's own predicates, so a client that recomputed either would be a second
 * opinion disagreeing with the screen the planner opens next.
 *
 * Shared between the list column and the detail header so the same order is not two chips on
 * two screens one click apart, the way `demandClassBadge` and `salesOrderStatusVariant` are.
 */
import type { StatusBadgeVariant } from '@/lib/status-badge';

export interface SalesOrderPlannedBadge {
  variant: StatusBadgeVariant;
  label: string;
}

/**
 * The four states, and nothing between them.
 *
 * NOTHING TO PLAN reads a dash rather than "Planned": an order whose every line is cancelled
 * or already marked no purchase needed was never planned, and a green chip claiming it was
 * would be the list agreeing to something nobody decided. It is also what an order looks like
 * before the counts arrive (both absent), which is the same honest answer.
 */
export function salesOrderPlannedBadge(
  plannedLines: number | null | undefined,
  plannableLines: number | null | undefined,
): SalesOrderPlannedBadge {
  const plannable = Number(plannableLines ?? 0);
  const planned = Number(plannedLines ?? 0);
  if (!Number.isFinite(plannable) || plannable <= 0) {
    return { variant: 'secondary', label: '-' };
  }
  if (planned >= plannable) return { variant: 'success', label: 'Planned' };
  if (planned <= 0) return { variant: 'destructive', label: 'Not planned' };
  return { variant: 'warning', label: `Partly ${planned}/${plannable}` };
}
