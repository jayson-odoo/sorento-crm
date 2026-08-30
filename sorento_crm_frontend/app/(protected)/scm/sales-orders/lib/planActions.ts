import { CalendarRange } from 'lucide-react';
import type { ToolbarAction } from '@/components/ui/data-grid-list-toolbar';

/**
 * "Plan selected (N)" - the sales-order list's way onto the fulfilment board.
 *
 * It lives in the toolbar's own **Start** menu, beside Upload sales orders, and NOT in the
 * bulk strip. The strip only exists once rows are ticked, so an action that lives there
 * cannot be found by someone who has not already guessed it is there - and when it refused
 * (over the board's bound) it refused as a greyed-out button whose reason was a hover away,
 * which is indistinguishable from a dead click.
 *
 * Start is where a day's work begins (the captain, 27 Aug): put the book in, or take a set
 * of orders to the board. In the menu the item is always present, always counts what is
 * selected, and states its refusal on itself.
 *
 * There is no plan ENTITY behind it. The fulfilment board is a URL
 * (`/project-sales/fulfilment-planning?orders=SO1,SO2`) and stays one, so this action
 * navigates and saves nothing: nothing is created by pressing it, and the same link can be
 * kept or sent.
 *
 * Two refusals, and they say different things:
 *
 * * with nothing ticked, and over the board's own bound, the item is DISABLED with the
 *   reason on it rather than hidden - the user is entitled to know the action exists and
 *   what it wants from them;
 * * without the permission the board's page requires, nothing renders at all. Offering a
 *   door that answers 403 is worse than not offering it.
 */
export interface PlanActionState {
  selectedCount: number;
  /** Whether the caller holds the permission the board's own page is gated on. */
  canPlan: boolean;
  /** The board's `MAX_BOARD_SELECTION`. */
  max: number;
}

export interface PlanActionHandlers {
  onPlan: () => void;
}

export function buildPlanActions(
  state: PlanActionState,
  handlers: PlanActionHandlers,
): ToolbarAction[] {
  if (!state.canPlan) return [];
  const nothingPicked = state.selectedCount < 1;
  const tooMany = state.selectedCount > state.max;
  return [
    {
      key: 'plan-selected',
      // The count is in the label, not only in the refusal: the menu is opened away from
      // the ticked rows, so it has to say how many are going.
      label: `Plan selected (${state.selectedCount})`,
      icon: CalendarRange,
      onClick: handlers.onPlan,
      disabled: nothingPicked || tooMany,
      disabledReason: nothingPicked
        ? 'Tick the sales orders to plan first.'
        : tooMany
          ? `The planning board takes up to ${state.max} orders at a time. ` +
            `${state.selectedCount} are selected.`
          : undefined,
    },
  ];
}
