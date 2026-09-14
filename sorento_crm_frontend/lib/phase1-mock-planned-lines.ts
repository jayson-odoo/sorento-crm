/**
 * PHASE 1 MOCK - DELETE IN PHASE 2 (`PLAN-fulfilment-board-plans-delivered-lines.md`).
 *
 * The frontend for S3 and S4 is built before any backend exists for it, so the two new facts
 * have to come from somewhere: the sales order's `planned_lines` / `plannable_lines`, and a
 * board row decided by an order inquiry rather than by a board decision (`covered: true`,
 * `decision: null`, `order_inquiry` naming it). This file is the only place they come from.
 *
 * IT DECORATES THE REAL RESPONSE, it does not replace it. Every other field on the screen is
 * the server's own, so what is verified in the browser is the real list, the real detail and
 * the real board with exactly the two new facts layered on - rather than a fabricated page
 * that would agree with itself whatever the contract turned out to be.
 *
 * OFF UNLESS ASKED FOR. `NEXT_PUBLIC_PHASE1_MOCK` is unset everywhere but a Phase 1 lane's own
 * `.env.local`, so a build that shipped this file by accident still shows the server's answer.
 *
 * Modes:
 * - `1`        decorate the list, the detail and the board (the ordinary Phase 1 run)
 * - `empty-window` the board returns no cells while the selection still holds lines (AC-S3-4)
 * - `empty-board`  the board returns no cells and no lines at all (AC-S3-1)
 *
 * PHASE 2 REMOVES: this file, its three call sites in `salesOrderService` and
 * `fulfilmentPlanningService`, and the env var.
 */
import type { SalesOrder } from '@/app/(protected)/scm/types/scm.types';
import type {
  BoardContribution,
  PlanningBoard,
} from '@/app/(protected)/project-sales/_shared/types/fulfilmentPlanning.types';

type Phase1MockMode = 'off' | 'on' | 'empty-window' | 'empty-board';

function mode(): Phase1MockMode {
  const raw = (process.env.NEXT_PUBLIC_PHASE1_MOCK ?? '').trim();
  if (raw === '1' || raw === 'true') return 'on';
  if (raw === 'empty-window') return 'empty-window';
  if (raw === 'empty-board') return 'empty-board';
  return 'off';
}

/** Stable per order number, so a reload shows the same pill and a screenshot is evidence. */
function hash(text: string): number {
  let total = 0;
  for (let index = 0; index < text.length; index += 1) {
    total = (total * 31 + text.charCodeAt(index)) % 100000;
  }
  return total;
}

/**
 * The two counts, spread across the four states this lane has to render.
 *
 * A real backend counts them off the board's own predicates; here the order number picks the
 * state, so one page of the list shows Planned, Partly, Not planned and the dash together and
 * none of the four has to be hunted for.
 */
function countsFor(order: SalesOrder): { planned_lines: number; plannable_lines: number } {
  const lines = order.line_count ?? order.lines?.length ?? 0;
  const bucket = hash(order.so_number ?? '') % 4;
  if (bucket === 3 || lines === 0) return { planned_lines: 0, plannable_lines: 0 };
  if (bucket === 0) return { planned_lines: lines, plannable_lines: lines };
  if (bucket === 2) return { planned_lines: 0, plannable_lines: lines };
  return { planned_lines: Math.max(1, Math.floor(lines / 2)), plannable_lines: lines };
}

export function mockSalesOrderPlanning<T extends SalesOrder>(order: T): T {
  if (mode() === 'off') return order;
  return { ...order, ...countsFor(order) };
}

export function mockSalesOrderListPlanning<T extends { data?: SalesOrder[] }>(page: T): T {
  if (mode() === 'off' || !Array.isArray(page.data)) return page;
  return { ...page, data: page.data.map((row) => mockSalesOrderPlanning(row)) };
}

/**
 * One board row decided by the BOOK rather than by a board (AC-S3-2), and the two empty states.
 *
 * The first contribution nothing has been decided for is turned into an inquiry-decided row:
 * covered, no composition, an inquiry naming it, and nothing proposed - which is exactly what
 * S2 will send once the server knows the rule.
 */
export function mockPlanningBoard(board: PlanningBoard): PlanningBoard {
  const current = mode();
  if (current === 'off') return board;
  if (current === 'empty-board') return { ...board, cells: [], line_count: 0 };
  if (current === 'empty-window') {
    return { ...board, cells: [], line_count: Math.max(board.line_count ?? 0, 7) };
  }

  // The board carries its lines TWICE - flat in `contributions`, windowed in `cells` - and
  // the list view reads the flat one while the grid reads the cells. The row is chosen once
  // and applied to both by key, or the two readings of one board would disagree about it.
  const target = board.contributions.find(
    (entry) => !entry.covered && !entry.unplannable && !entry.cancelled,
  );
  if (!target) return board;
  const decide = <T extends BoardContribution>(entry: T): T =>
    entry.key === target.key
      ? {
          ...entry,
          covered: true,
          decision: null,
          proposed: null,
          trail: [],
          sources: [],
          qty_proposed_reserve: '0',
          qty_proposed_incoming: '0',
          qty_proposed_buy: '0',
          order_inquiry: {
            inquiry_no: 'OI-000418',
            state: 'raised',
            ack_state: 'awaiting',
          },
        }
      : entry;

  return {
    ...board,
    contributions: board.contributions.map(decide),
    cells: board.cells.map((cell) => ({
      ...cell,
      contributions: cell.contributions.map(decide),
    })),
  };
}
