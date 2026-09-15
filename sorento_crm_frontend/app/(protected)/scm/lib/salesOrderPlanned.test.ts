/**
 * AC-S4-6 - the four states of the Planned chip, and nothing between them.
 *
 * `PLAN-fulfilment-board-plans-delivered-lines.md` S4. The chip answers the owner's question
 * off SO421404 (14 September 2026): "how do I know if the order is fully planned from the list
 * itself?" The list already names the order inquiries raised against an order, which says what
 * purchasing was TOLD; nothing said whether anybody had decided where the stock comes from.
 *
 * TWO COUNTS OFF THE SERVER, never re-derived here - `plannable_lines` is what the fulfilment
 * board would admit and `planned_lines` how many of those are settled, both counted by the
 * board's own predicates. A client that recomputed either would be a second opinion
 * disagreeing with the screen the planner opens next.
 *
 * The same function backs the list column and the detail header (AC-S4-7), so the same order
 * cannot be two different chips on two screens one click apart.
 */
import { describe, expect, it } from 'vitest';

import { salesOrderPlannedBadge } from './salesOrderPlanned';

describe('salesOrderPlannedBadge', () => {
  it('reads Planned, in success, when every plannable line is decided', () => {
    expect(salesOrderPlannedBadge(3, 3)).toEqual({ variant: 'success', label: 'Planned' });
  });

  it('reads Partly n/m, in warning, when some are', () => {
    expect(salesOrderPlannedBadge(2, 3)).toEqual({ variant: 'warning', label: 'Partly 2/3' });
  });

  /**
   * SO421404's own state: Completed, three of three delivered, and nobody ever decided where
   * a single unit came from. Destructive, because it is the row that needs somebody.
   */
  it('reads Not planned, in destructive, when none are', () => {
    expect(salesOrderPlannedBadge(0, 3)).toEqual({
      variant: 'destructive',
      label: 'Not planned',
    });
  });

  /**
   * NOTHING TO PLAN IS NOT "PLANNED". An order whose every line is cancelled or already marked
   * no purchase needed was never planned, and a green chip claiming it was would have the list
   * agreeing to a decision nobody made.
   */
  it('reads a dash, muted, when there is nothing to plan', () => {
    expect(salesOrderPlannedBadge(0, 0)).toEqual({ variant: 'secondary', label: '-' });
  });

  /**
   * The same honest answer before the counts arrive. A row whose fields are absent - an older
   * cached page, a response the server has not grown the fields on yet - must not claim
   * anything either way.
   */
  it('reads a dash when the counts are absent', () => {
    expect(salesOrderPlannedBadge(undefined, undefined)).toEqual({
      variant: 'secondary',
      label: '-',
    });
    expect(salesOrderPlannedBadge(null, null)).toEqual({
      variant: 'secondary',
      label: '-',
    });
  });
});
