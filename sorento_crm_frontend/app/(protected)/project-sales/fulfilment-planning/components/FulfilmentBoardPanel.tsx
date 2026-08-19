'use client';

import * as React from 'react';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { ArrowLeft, CheckCheck, LayoutGrid, List, PackageSearch, Search, X } from 'lucide-react';
import {
  Alert,
  AlertContent,
  AlertDescription,
  AlertIcon,
  AlertTitle,
} from '@/components/ui/alert';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import {
  useConfirmManyMutation,
  useFulfilmentPlanningMutations,
  useReconciliationMutations,
  usePlanningBoard,
} from '../../_shared/hooks/useFulfilmentPlanning';
import { ConfirmSupplyError } from '../../_shared/services/fulfilmentPlanningService';
import {
  boardAxis,
  bucketLabelText,
  commitPreviewFor,
  rowMatchesSearch,
  confirmLinesFor,
  plannedLineCount,
  shiftedDayWindow,
  standingsFor,
  unpostableDecidedFor,
  type ContributionOwners,
  type UnpostableLine,
  type UnpostableReason,
} from '../../_shared/lib/fulfilmentBoard';
import type {
  BoardCell,
  BoardCommitPreview,
  BoardContribution,
  BoardDecision,
  BoardDraft,
  BoardGranularity,
  BoardOrderStanding,
  BoardRowAxis,
  ConfirmManyOrderResult,
  SupplyFailingLine,
} from '../../_shared/types/fulfilmentPlanning.types';
import { BoardCellBreakdownDialog } from './BoardCellBreakdownDialog';
import { FulfilmentBoardListView } from './FulfilmentBoardListView';
import { FulfilmentBoardMatrix } from './FulfilmentBoardMatrix';

/** Persisted in the URL as `?view=list` (D2). Grid is the default the board shipped as. */
type BoardView = 'grid' | 'list';

function boardViewFrom(value: string | null): BoardView {
  return value === 'list' ? 'list' : 'grid';
}

/** The calendar control the captain asked for: day, week or month (PLAN 13.3). */
const GRANULARITY_OPTIONS = [
  { value: 'day', label: 'By day' },
  { value: 'week', label: 'By week' },
  { value: 'month', label: 'By month' },
];

/**
 * The granularity a URL may name, and what an unknown one becomes.
 *
 * Guarded the way the server guards it: a link carrying `granularity=fortnightly` opens the
 * week board rather than asking for a cut nothing can produce. A hand-edited or stale link is
 * the normal case for a shareable URL, not an attack.
 */
const GRANULARITIES: BoardGranularity[] = ['day', 'week', 'month'];

/**
 * What the vertical axis can be, and what the reader calls each one.
 *
 * Product first because it is the default and the shape the board shipped as; the other three
 * are the captain's own list, in the order they asked for them.
 */
const ROW_AXIS_OPTIONS = [
  { value: 'product', label: 'Product' },
  { value: 'sales_order', label: 'Sales order' },
  { value: 'customer', label: 'Customer' },
  { value: 'project', label: 'Project' },
];

/** Singular and plural for the "N of M" line, so it names what the rows actually are. */
const ROW_AXIS_NOUNS: Record<BoardRowAxis, string> = {
  product: 'products',
  sales_order: 'sales orders',
  customer: 'customers',
  project: 'projects',
};

const ROW_AXES: BoardRowAxis[] = ['product', 'sales_order', 'customer', 'project'];

function rowAxisFrom(value: string | null): BoardRowAxis {
  return ROW_AXES.includes(value as BoardRowAxis) ? (value as BoardRowAxis) : 'product';
}

function granularityFrom(value: string | null): BoardGranularity {
  return GRANULARITIES.includes(value as BoardGranularity)
    ? (value as BoardGranularity)
    : 'week';
}

/**
 * Planning several sales orders at once (PLAN section 13).
 *
 * The board is a LENS. It reads across the selection and writes nothing of its own: approve /
 * amend / reject go into a draft held here, and the thing that commits is still the existing
 * per-order confirmation, one call per order, atomic across that order's lines (13.4, 13.6).
 *
 * Confirm is NOT gated on an order being fully decided (13.4, the captain overruling this plan's
 * own recommendation): a planner commits the lines they are sure about precisely so the undecided
 * ones keep flowing to reorder planning. So the rail's "4 of 12 lines decided" is INFORMATION, not
 * a gate, and beside it the screen states plainly what each Confirm would leave behind and where
 * that demand goes. A button that silently committed four lines and dropped eight would be the
 * same lie in the other direction.
 */
export function FulfilmentBoardPanel({
  soNumbers,
  onBack,
}: {
  soNumbers: string[];
  onBack: () => void;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [granularity, setGranularity] = React.useState<BoardGranularity>(() =>
    granularityFrom(searchParams.get('granularity')),
  );
  /**
   * Narrowing the PRODUCT ROWS (the captain: "i need the search here also btw").
   *
   * A filter over one already-fetched payload, never a refetch and never a change to the
   * selection: the board is a single response, and asking the server again for a subset of
   * rows it already sent would be slower and could disagree with the cells beside it.
   */
  const [productSearch, setProductSearch] = React.useState(
    () => searchParams.get('product') ?? '',
  );
  const [rowAxis, setRowAxis] = React.useState<BoardRowAxis>(() =>
    rowAxisFrom(searchParams.get('rows')),
  );
  /**
   * Grid | List (D2, PLAN-demo-followups-19aug-ladder-v2 "a list view of the board so
   * Approve all can be seen from an overview"). Persisted in the URL the same way the other
   * dials are, so a link to the list view is shareable.
   */
  const [view, setView] = React.useState<BoardView>(() => boardViewFrom(searchParams.get('view')));
  const [draft, setDraft] = React.useState<BoardDraft>({});
  const [openCell, setOpenCell] = React.useState<BoardCell | null>(null);
  /** Which 30-day window the day view is showing. Undefined lets the server choose the first. */
  const [dayWindow, setDayWindow] = React.useState<string | undefined>(undefined);

  // The granularity and the product filter travel in the URL, beside the selection the
  // worklist put there, so the WHOLE board is one link (PLAN 13.2, 13.3). `replace`, not
  // `push`: turning a dial is not a place in history to go back to.
  React.useEffect(() => {
    const next = new URLSearchParams(searchParams.toString());
    if (granularity === 'week') next.delete('granularity');
    else next.set('granularity', granularity);
    // Absent when it is the default, the same idiom as the granularity, so a link carries only
    // what the sender actually changed.
    if (rowAxis === 'product') next.delete('rows');
    else next.set('rows', rowAxis);
    if (productSearch.trim()) next.set('product', productSearch.trim());
    else next.delete('product');
    if (view === 'grid') next.delete('view');
    else next.set('view', view);
    const query = next.toString();
    if (query === searchParams.toString()) return;
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }, [granularity, rowAxis, productSearch, view, pathname, router, searchParams]);

  const board = usePlanningBoard(
    soNumbers,
    granularity,
    // Always the LIVE policy. The preview was a what-if for showing a fair weighting before one
    // was switched on; the fair policy is now the live one, the offer was retired with it, and
    // the banner that carried the way back went with the banner itself.
    false,
    dayWindow ? { dayWindow } : {},
  );

  /**
   * Move the day window by a whole window at a time.
   *
   * The FIRST window is the server's: it opens on the earliest date still to come, falling
   * back to the earliest owed when everything is past. Once the planner has moved it, the
   * window THEY asked for is the anchor, and the step is the contract's thirty days - never
   * the columns that happened to come back, so a stretch nobody owes anything in is still a
   * page and no day is skipped or shown twice.
   *
   * Day is the only granularity with a window. Week and month need none: only periods actually
   * owed become columns, so the 50-order cap tops out around 57 week or 24 month columns, and
   * a control to page through them would be a knob for a problem nobody has.
   */
  const shiftWindow = React.useCallback(
    (direction: 1 | -1) => {
      const anchor =
        dayWindow ??
        board.data?.dateBuckets.find((bucket) => bucket.kind === 'dated' && bucket.start)?.start ??
        board.data?.as_of;
      if (!anchor) return;
      setDayWindow(shiftedDayWindow(anchor, direction));
    },
    [board.data, dayWindow],
  );

  const decide = React.useCallback((key: string, decision: BoardDecision | null) => {
    setDraft((current) => {
      const next = { ...current };
      if (decision) next[key] = decision;
      else delete next[key];
      return next;
    });
  }, []);

  const decidedKeys = React.useMemo(() => new Set(Object.keys(draft)), [draft]);

  const { confirm } = useReconciliationMutations();
  const { adopt } = useFulfilmentPlanningMutations();
  /** Which order is in flight, and what the server refused, per order. */
  const [confirming, setConfirming] = React.useState<string | null>(null);
  const [refusals, setRefusals] = React.useState<Record<string, SupplyFailingLine[]>>({});

  /**
   * Commit one order's decided lines through the existing per-order confirmation.
   *
   * The board writes nothing of its own (13.4): this is the SAME endpoint the sheet posts to,
   * so there is one write path and one set of invariants. Partial by construction - a line the
   * body does not name and no active revision covers is left undecided and keeps flowing to
   * reorder planning. The body names ONLY what was decided or amended on this screen; a line
   * the active revision already covers is carried into the new revision by the server, so the
   * board never re-posts it (a day window could not even see all of them, and a re-post was
   * re-judged against live facts).
   *
   * On success the confirmed keys leave the draft, because they are in the database now and a
   * draft that still claimed them would offer to confirm them twice. On a REFUSAL the draft is
   * untouched: the planner composed that, the server rejected it, and making them do it again
   * is the one outcome that would teach them not to use the board.
   */
  const confirmOrder = React.useCallback(
    async (standing: BoardOrderStanding) => {
      if (!board.data) return;
      setConfirming(standing.sales_order_id);
      setRefusals((current) => ({ ...current, [standing.sales_order_id]: [] }));

      let psoId = standing.project_sales_order_id ?? null;
      let contributions = board.data.contributions;

      try {
        // ADOPT FIRST when there is no planning record. Deciding lines and pressing Confirm is
        // the whole act as far as the planner is concerned, and refusing at the last step after
        // they have composed nine orders is the dead end this exists to remove. Adoption is
        // idempotent, so a second press or a second user lands on the same record.
        if (!psoId) {
          let adopted;
          try {
            adopted = await adopt.mutateAsync(standing.sales_order_id);
          } catch (error) {
            setRefusals((current) => ({
              ...current,
              [standing.sales_order_id]: [
                {
                  reason: `Could not start planning this sales order: ${
                    error instanceof Error ? error.message : 'the request was refused.'
                  }`,
                },
              ],
            }));
            return;
          }
          psoId = adopted.project_sales_order_id;
          // The board MUST be re-read before the body is built: `project_line_id` is null on
          // every contribution until the mirror lines exist, so anything built a moment ago
          // names nothing. The ids are asked for, never guessed.
          const fresh = await board.refetch();
          if (!fresh.data) {
            setRefusals((current) => ({
              ...current,
              [standing.sales_order_id]: [
                { reason: 'Planning started, but the board could not be re-read. Try again.' },
              ],
            }));
            return;
          }
          contributions = fresh.data.contributions;
        }

        const lines = confirmLinesFor(contributions, standing.sales_order_id, draft);
        if (lines.length === 0) {
          setRefusals((current) => ({
            ...current,
            [standing.sales_order_id]: [
              { reason: 'None of the decided lines could be confirmed against this order yet.' },
            ],
          }));
          return;
        }

        await confirm.mutateAsync({ psoId: psoId as string, body: { lines } });
        const committed = new Set(lines.map((line) => line.project_line_id));
        setDraft((current) => {
          const next = { ...current };
          for (const contribution of contributions) {
            if (
              contribution.project_line_id &&
              committed.has(contribution.project_line_id) &&
              next[contribution.key]
            ) {
              delete next[contribution.key];
            }
          }
          return next;
        });
      } catch (error) {
        if (error instanceof ConfirmSupplyError && error.failingLines.length > 0) {
          setRefusals((current) => ({
            ...current,
            [standing.sales_order_id]: error.failingLines,
          }));
        } else {
          // The mutation already toasted the message; this is the fallback for a refusal that
          // named no line, so the row still says something happened.
          setRefusals((current) => ({
            ...current,
            [standing.sales_order_id]: [
              { reason: error instanceof Error ? error.message : 'The confirmation was refused.' },
            ],
          }));
        }
      } finally {
        setConfirming(null);
      }
    },
    [board, confirm, adopt, draft],
  );

  /**
   * Which order each contribution key belongs to, ACCUMULATED across every board shown.
   *
   * A verdict is only ever given on a cell that was on screen, so every draft key passes
   * through here once. Rebuilding this from the current board instead would drop a verdict the
   * moment its cell left the day window, and the counter would fall as the planner scrolled.
   * The key is stored, never parsed: the server owns its format (deviation 5).
   */
  const ledger = React.useRef<{ owners: ContributionOwners; covered: Set<string> }>({
    owners: new Map(),
    // The lines an ACTIVE decision already covers, which are decided in the DATABASE rather
    // than in the draft. Kept beside `owners` because the order card counts both, and REMOVED
    // again when a board says a line it once covered is no longer covered - a revision can be
    // superseded or challenged, and a "decided" that only ever accumulates would go on
    // claiming a decision that has been retired.
    covered: new Set(),
  });
  /**
   * The ledger brought up to date with THIS board, once per board rather than on every render:
   * folding a board in is idempotent, so a repeated pass changes nothing, but a pass on every
   * render was work in the render body that a memo keyed on the board does not need to be.
   */
  const ownership = React.useMemo(() => {
    const { owners, covered } = ledger.current;
    for (const contribution of board.data?.contributions ?? []) {
      owners.set(contribution.key, contribution.sales_order_id);
      if (contribution.covered) covered.add(contribution.key);
      else covered.delete(contribution.key);
    }
    return { owners, covered, board: board.data };
  }, [board.data]);

  /**
   * The standings are the SERVER's, off `board.orders`, which counts every row of the
   * selection. Only the verdicts are ours.
   *
   * Counting them from `cells` was a live defect: at day granularity the cells are a 30-day
   * window, so a forty-line order read "3 of 3 lines decided" and the Confirm beside it
   * promised to leave nothing behind.
   */
  const standings = React.useMemo<BoardOrderStanding[]>(() => {
    if (!ownership.board) return [];
    return standingsFor(ownership.board.orders, ownership.owners, draft, ownership.covered);
  }, [ownership, draft]);

  /**
   * What each order's Confirm would actually post, and what it would leave.
   *
   * `committing` is the length of the BODY, not the count of verdicts: a decided line whose
   * sales order has no mirror for it yet cannot be posted, and a button promising to confirm it
   * would be describing something the body deliberately omits.
   */
  const previews = React.useMemo<Record<string, BoardCommitPreview>>(() => {
    if (!board.data) return {};
    const contributions = board.data.contributions;
    return Object.fromEntries(
      standings.map((standing) => [
        standing.sales_order_id,
        commitPreviewFor(
          standing,
          // On an adopted order the body is the truth; on one that has not been adopted the
          // body cannot exist yet, so the verdicts are, and the press adopts before building.
          standing.project_sales_order_id
            ? confirmLinesFor(contributions, standing.sales_order_id, draft).length
            : plannedLineCount(contributions, standing.sales_order_id, draft),
        ),
      ]),
    );
  }, [standings, board.data, draft]);

  /** Decided lines this confirmation cannot carry, per order, named on the rail with why. */
  const unpostable = React.useMemo<Record<string, UnpostableLine[]>>(() => {
    if (!board.data) return {};
    const contributions = board.data.contributions;
    return Object.fromEntries(
      standings.map((standing) => [
        standing.sales_order_id,
        unpostableDecidedFor(
          contributions,
          standing.sales_order_id,
          draft,
          Boolean(standing.project_sales_order_id),
        ),
      ]),
    );
  }, [standings, board.data, draft]);

  /**
   * Every contributing line of the WHOLE selection, unwindowed - the same population "Approve
   * all" and the List view (D2) act on. The server's own top-level `contributions`, never
   * `cells[].contributions`: a cell only exists for a bucket that made it onto screen, and at
   * day granularity that is the 30-day window (`DAY_WINDOW_COLUMNS`), not the whole selection -
   * flattening the cells silently dropped every line outside it, so "Approve all" and the
   * confirm-all dialog undercounted (13.5's own reason `standings` reads `board.orders` instead
   * of the cells).
   */
  const allContributions = React.useMemo<BoardContribution[]>(
    () => board.data?.contributions ?? [],
    [board.data],
  );

  /**
   * Approve all (D3): every UNDECIDED, approvable proposal becomes `approved` in the draft.
   *
   * "Approvable" skips exactly what a single Approve press already refuses to touch: a line
   * whose sales order states no location (`unplannable`, AC-FP16), and a line an active
   * decision already covers and the planner has not amended (`covered` with no draft entry -
   * approving a decision already taken would be a no-op that reads as new work). A line that
   * ALREADY carries a verdict - approved, amended or rejected - is left exactly as the planner
   * left it: Approve all fills in the blanks, it does not overwrite a decision.
   */
  const approveAll = React.useCallback(() => {
    setDraft((current) => {
      const next = { ...current };
      for (const contribution of allContributions) {
        if (contribution.unplannable || contribution.covered) continue;
        if (next[contribution.key]) continue;
        next[contribution.key] = { verdict: 'approved' };
      }
      return next;
    });
  }, [allContributions]);

  /**
   * "N approved · M undecided" (D3): counted over the SAME approvable population `approveAll`
   * fills, so the toolbar sentence and what a press of the button would do never disagree.
   * `approved` counts every non-rejected verdict - approved AND amended - because both are
   * decisions "Confirm all approved" is about to write; a rejection is a decision too, but it
   * commits nothing, so it is neither approved nor undecided here.
   */
  const approvalSummary = React.useMemo(() => {
    let approved = 0;
    let undecided = 0;
    const orderIds = new Set<string>();
    for (const contribution of allContributions) {
      if (contribution.unplannable || contribution.covered) continue;
      const decision = draft[contribution.key];
      if (decision && decision.verdict !== 'rejected') {
        approved += 1;
        orderIds.add(contribution.sales_order_id);
      } else if (!decision) {
        undecided += 1;
      }
    }
    return { approved, undecided, orderCount: orderIds.size };
  }, [allContributions, draft]);

  const confirmMany = useConfirmManyMutation();
  const [confirmAllOpen, setConfirmAllOpen] = React.useState(false);
  const [confirmingAll, setConfirmingAll] = React.useState(false);
  const [batchResults, setBatchResults] = React.useState<ConfirmManyOrderResult[] | null>(null);

  /**
   * "Confirm all approved" (D3): one call, grouped per order, each order writing in its OWN
   * transaction server-side (`confirm_many`) - so one order's refusal never takes the others
   * down. Any order in the batch that has not been adopted yet is adopted first, exactly the
   * step `confirmOrder` already takes for a single order; the board is re-read once afterwards
   * so the fresh mirror lines can be named in the payload (adoption fills `project_line_id`,
   * which is null until then).
   */
  const runConfirmAll = React.useCallback(async () => {
    if (!board.data) return;
    setConfirmAllOpen(false);
    setConfirmingAll(true);
    setBatchResults(null);
    try {
      let liveBoard = board.data;
      let contributions = allContributions;

      const wantedOrders = new Set(
        contributions
          .filter((contribution) => {
            const decision = draft[contribution.key];
            if (!decision || decision.verdict === 'rejected') return false;
            if (contribution.covered && decision.verdict !== 'amended') return false;
            return true;
          })
          .map((contribution) => contribution.sales_order_id),
      );
      if (wantedOrders.size === 0) return;

      let adoptedAny = false;
      for (const order of liveBoard.orders) {
        if (!wantedOrders.has(order.sales_order_id) || order.project_sales_order_id) continue;
        try {
          await adopt.mutateAsync(order.sales_order_id);
          adoptedAny = true;
        } catch {
          // Left out of the batch below: with no pso_id there is nothing to post for it.
        }
      }
      if (adoptedAny) {
        const fresh = await board.refetch();
        if (fresh.data) {
          liveBoard = fresh.data;
          contributions = liveBoard.contributions;
        }
      }

      const psoIdBySalesOrder = new Map(
        liveBoard.orders
          .filter((order) => order.project_sales_order_id)
          .map((order) => [order.sales_order_id, order.project_sales_order_id as string]),
      );

      const orders: { pso_id: string; lines: ReturnType<typeof confirmLinesFor> }[] = [];
      for (const salesOrderId of wantedOrders) {
        const psoId = psoIdBySalesOrder.get(salesOrderId);
        if (!psoId) continue;
        const lines = confirmLinesFor(contributions, salesOrderId, draft);
        if (lines.length > 0) orders.push({ pso_id: psoId, lines });
      }
      if (orders.length === 0) return;

      const result = await confirmMany.mutateAsync({ orders });
      setBatchResults(result.results);

      const committedPsoIds = new Set(
        result.results.filter((entry) => entry.ok).map((entry) => entry.pso_id),
      );
      const committedLineIds = new Set(
        orders
          .filter((order) => committedPsoIds.has(order.pso_id))
          .flatMap((order) => order.lines.map((line) => line.project_line_id)),
      );
      setDraft((current) => {
        const next = { ...current };
        for (const contribution of contributions) {
          if (
            contribution.project_line_id &&
            committedLineIds.has(contribution.project_line_id) &&
            next[contribution.key]
          ) {
            delete next[contribution.key];
          }
        }
        return next;
      });
    } catch {
      // The mutation's own `onError` already toasted the message; nothing here is left to say.
      // Caught only so the rejection does not float unhandled past this async click handler.
    } finally {
      setConfirmingAll(false);
    }
  }, [board, allContributions, draft, adopt, confirmMany]);

  /**
   * The rows on screen, and the rows the selection holds.
   *
   * Matching on the code AND the name, because a planner knows a product by either. The counts
   * this produces are about the FILTER; every headline number on this screen stays
   * selection-scoped, exactly as it does under the day window.
   */
  /**
   * The rows and cells for the chosen axis.
   *
   * On the PRODUCT axis these are the server's own, untouched: its cells carry the stock
   * position per product and location, which no client-side regrouping could reproduce. The
   * pivoted axes are the same contributions grouped differently - one payload, one idea of what
   * a line is.
   */
  const axis = React.useMemo(() => {
    const cells = board.data?.cells ?? [];
    if (rowAxis === 'product') {
      return {
        rows: (board.data?.productRows ?? []).map((row) => ({
          key: row.item_code,
          label: row.item_code,
          description: row.description,
        })),
        cells,
      };
    }
    return boardAxis(rowAxis, cells);
  }, [board.data, rowAxis]);

  /** Lines per row, so the search can ask whether ANY of a row's lines matches. */
  const linesByRow = React.useMemo(() => {
    const map = new Map<string, BoardContribution[]>();
    for (const cell of axis.cells) {
      const key = cell.row_key ?? cell.item_code;
      const held = map.get(key);
      if (held) held.push(...cell.contributions);
      else map.set(key, [...cell.contributions]);
    }
    return map;
  }, [axis]);

  const visibleProductRows = React.useMemo(
    () =>
      axis.rows.filter((row) =>
        rowMatchesSearch(row, linesByRow.get(row.key) ?? [], productSearch),
      ),
    [axis, linesByRow, productSearch],
  );

  const filtering = productSearch.trim().length > 0;

  /**
   * Orders the link asked for that the board came back without.
   *
   * A shared link can name an order that has since been delivered or closed, or one that was
   * mistyped. Opening a board of four when the link asked for five, and saying nothing, is the
   * quiet subtraction that makes a shared link untrustworthy. The message states what is
   * observable and does not guess which of the two happened.
   */
  const missingOrders = React.useMemo(() => {
    if (!board.data) return [];
    const present = new Set(board.data.orders.map((order) => order.so_number));
    return soNumbers.filter((soNumber) => !present.has(soNumber));
  }, [board.data, soNumbers]);

  const bucketLabel = React.useMemo(() => {
    const map = new Map<string, string>();
    // Through the same de-jargoning the column headers go through: the dialog title reads the
    // same label, and it was still saying "w/c 24 Nov 2025" after the headers had stopped.
    for (const bucket of board.data?.dateBuckets ?? []) {
      map.set(bucket.key, bucketLabelText(bucket.label));
    }
    return map;
  }, [board.data]);

  // The cell the dialog is showing has to be re-read from the board on every render, or the
  // decision pills inside it would keep the shape they had when it was opened.
  const liveCell = React.useMemo(() => {
    if (!openCell || !board.data) return null;
    // Re-read from the cells of the CURRENT axis, keyed the way that axis keys them. Looking it
    // up in the server's product cells found nothing on a pivoted board, so the dialog simply
    // did not open.
    const openKey = openCell.row_key ?? openCell.item_code;
    return (
      axis.cells.find(
        (cell) =>
          (cell.row_key ?? cell.item_code) === openKey &&
          cell.bucket_key === openCell.bucket_key,
      ) ?? null
    );
  }, [openCell, board.data, axis]);

  /**
   * How many LINES of the selection are already past their delivery date.
   *
   * The server's two selection-scoped totals, read straight. NOT summed off the cells: cells
   * are what a window is showing, so the same board reported a different number on day than on
   * week and reported none at all when the window was scrolled somewhere empty. The per-cell
   * `past_count` is still right for its own cell; it was only wrong as a banner source.
   *
   * It also is not the count of TINTED columns, which is a different question: a line due
   * yesterday sits in the week containing `as_of`, whose period has not ended, so that week is
   * not tinted while the line is certainly late.
   */
  const pastTotal = {
    lines: board.data?.past_line_count ?? 0,
    allLines: board.data?.line_count ?? 0,
  };

  return (
    <div className="space-y-4">
      {/* Title left, actions right, and the row WRAPS. A plain `items-center justify-between`
          does not, so at narrow widths the controls landed on top of the title and pushed the
          page sideways - which is what the captain screenshotted. */}
      <div
        data-testid="board-header"
        className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
      >
        <h2
          data-testid="board-header-title"
          className="min-w-0 text-lg font-semibold break-words"
        >
          {`Planning ${soNumbers.length} sales orders together`}
        </h2>
        <div className="relative w-full sm:w-64">
          <Search
            className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            placeholder="Search sales order, customer, project or product"
            aria-label="Search sales order, customer, project or product"
            value={productSearch}
            onChange={(event) => setProductSearch(event.target.value)}
            className="w-full ps-9"
          />
          {productSearch.length > 0 && (
            <Button
              mode="icon"
              variant="dim"
              aria-label="Clear the product search"
              className="absolute end-1.5 top-1/2 h-6 w-6 -translate-y-1/2"
              onClick={() => setProductSearch('')}
            >
              <X />
            </Button>
          )}
        </div>

        <div
          data-testid="board-header-actions"
          className="flex w-full flex-wrap items-center gap-2 sm:w-auto"
        >
          {granularity === 'day' && (
            <>
              <Button type="button" variant="outline" size="sm" onClick={() => shiftWindow(-1)}>
                Earlier days
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={() => shiftWindow(1)}>
                Later days
              </Button>
            </>
          )}
          {/* Labelled in words, because "Product / Sales order / Customer / Project" in a bare
              select says nothing about what it does to the grid. The captain wrote it as
              "Rows: Product | Sales order | Customer | Project", so that is what it reads. */}
          <div className="flex w-full items-center gap-2 sm:w-auto">
            <label htmlFor="rows" className="text-sm text-muted-foreground">
              Rows
            </label>
            <div className="w-full sm:w-40">
              <SearchableSelect
                id="rows"
                value={rowAxis}
                onChange={(value) => setRowAxis(value as BoardRowAxis)}
                options={ROW_AXIS_OPTIONS}
              />
            </div>
          </div>
          <div className="w-full sm:w-44">
            <SearchableSelect
              value={granularity}
              onChange={(value) => {
                // A window belongs to the view that scrolled it; carrying it into week or month
                // would silently pin those to a date the planner never chose.
                setDayWindow(undefined);
                setGranularity(value as BoardGranularity);
              }}
              options={GRANULARITY_OPTIONS}
            />
          </div>
          {/* Grid | List (D2): "how do I review it" - the grid answers what a product owes by
              date, the list answers what is about to be committed, across every order, in one
              scan. A toggle, not two screens, because it is the same draft either way. */}
          <div className="inline-flex rounded-md border border-input" role="group" aria-label="Board view">
            <Button
              type="button"
              size="sm"
              variant={view === 'grid' ? 'primary' : 'ghost'}
              className="rounded-e-none"
              aria-pressed={view === 'grid'}
              onClick={() => setView('grid')}
            >
              <LayoutGrid className="size-4" aria-hidden />
              Grid
            </Button>
            <Button
              type="button"
              size="sm"
              variant={view === 'list' ? 'primary' : 'ghost'}
              className="rounded-s-none border-s border-input"
              aria-pressed={view === 'list'}
              onClick={() => setView('list')}
            >
              <List className="size-4" aria-hidden />
              List
            </Button>
          </div>
          {/* Last in the row and `ghost`: going back is secondary to the control that decides
              what the board shows, and an outline button beside the select out-shouted it. */}
          <Button type="button" variant="ghost" size="sm" onClick={onBack}>
            <ArrowLeft className="size-4" aria-hidden />
            Back to the worklist
          </Button>
        </div>
      </div>

      {/* Approve all + Confirm all approved (D3). Its own row, above the grid/list, so it is
          visible whichever view is on screen - the captain's ask was "a list view of the
          board so Approve all can be seen from an overview", and the button that DOES the
          approving has to be reachable from both. */}
      {board.data && board.data.cells.length > 0 && (
        <div className="flex flex-col gap-2 rounded-lg border border-border px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between">
          <span className="text-sm text-muted-foreground tabular-nums">
            {`${approvalSummary.approved} approved · ${approvalSummary.undecided} undecided`}
          </span>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={approvalSummary.undecided === 0}
              onClick={approveAll}
            >
              <CheckCheck className="size-4" aria-hidden />
              Approve all
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={approvalSummary.approved === 0 || confirmingAll}
              onClick={() => setConfirmAllOpen(true)}
            >
              Confirm all approved
            </Button>
          </div>
        </div>
      )}

      {batchResults && (
        <div className="space-y-1 rounded-lg border border-border px-3 py-2.5">
          <p className="text-sm font-medium">
            {`Confirm all: ${batchResults.filter((r) => r.ok).length} of ${batchResults.length} orders confirmed`}
          </p>
          <ul className="space-y-1">
            {batchResults.map((result) => {
              const order = board.data?.orders.find(
                (candidate) => candidate.project_sales_order_id === result.pso_id,
              );
              const label = order?.so_number ?? result.pso_id;
              return (
                <li
                  key={result.pso_id}
                  className={`text-sm break-words ${result.ok ? 'text-emerald-700' : 'text-destructive'}`}
                >
                  {result.ok
                    ? `${label}: confirmed as revision ${result.decision_revision} (${result.inquiry_rows_created ?? 0} purchase row${(result.inquiry_rows_created ?? 0) === 1 ? '' : 's'} handed over)`
                    : `${label}: ${result.error ?? 'refused'}`}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {board.isError ? (
        <Alert variant="destructive" appearance="light">
          <AlertIcon>
            <AlertTriangle />
          </AlertIcon>
          <AlertContent>
            <AlertTitle>The planning board could not be loaded</AlertTitle>
            <AlertDescription>
              {board.error instanceof Error ? board.error.message : 'Try again in a moment.'}
              <div className="mt-3">
                <Button type="button" size="sm" variant="outline" onClick={() => board.refetch()}>
                  Try again
                </Button>
              </div>
            </AlertDescription>
          </AlertContent>
        </Alert>
      ) : board.isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-72 w-full" />
        </div>
      ) : !board.data || board.data.cells.length === 0 ? (
        <Card>
          <CardContent className="px-6 py-10 text-center">
            <PackageSearch className="mx-auto size-6 text-muted-foreground" aria-hidden />
            {/* No cells does NOT mean nothing is owed. A day window scrolled to a stretch
                nobody owes has no cells while the selection still holds every one of its
                lines, and "these orders owe nothing" would flatly contradict them. The
                selection-scoped total is the only thing that can tell the two apart. */}
            {(board.data?.line_count ?? 0) > 0 ? (
              <>
                <h3 className="mt-2 text-sm font-semibold">Nothing is owed in these dates</h3>
                <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                  {`The selection holds ${board.data?.line_count} lines on other dates.`}
                </p>
              </>
            ) : (
              <>
                <h3 className="mt-2 text-sm font-semibold">
                  These sales orders owe nothing that can be planned
                </h3>
                <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                  Every line of the selection is already delivered, closed or covered.
                </p>
              </>
            )}
          </CardContent>
        </Card>
      ) : (
        <>
          {missingOrders.length > 0 && (
            <Alert appearance="light">
              <AlertIcon>
                <AlertTriangle />
              </AlertIcon>
              <AlertContent>
                <AlertTitle>
                  {`${missingOrders.join(', ')} ${
                    missingOrders.length === 1 ? 'has' : 'have'
                  } nothing to plan on this board.`}
                </AlertTitle>
              </AlertContent>
            </Alert>
          )}

          {/* The fact, and only the fact. The columns and their tint say where those lines
              are; a paragraph explaining the tint would be a feature explanation in the UI,
              and a tint that needs one has failed. */}
          {pastTotal.lines > 0 && (
            <Alert appearance="light">
              <AlertIcon>
                <AlertTriangle />
              </AlertIcon>
              <AlertContent>
                <AlertTitle>
                  {`${pastTotal.lines} of ${pastTotal.allLines} lines are already past their delivery date`}
                </AlertTitle>
              </AlertContent>
            </Alert>
          )}

          {/* NO POLICY BANNER. It named the rule and listed its weights across the top of the
              board, and the captain's verdict on it was "this text is not needed at the top":
              it is not what anybody opens this screen to read, and it was there whether or not
              a question about ranking had been asked. The information is not lost - the rank
              popover on a row names the policy above its factor table, which is where somebody
              IS asking - see `BoardRankPopover` and PLAN 13.10. */}

          {view === 'list' ? (
            /* D2: one row per contributing line across every cell of the WHOLE selection, not
               the pivoted/windowed rows the grid shows - the point is an overview, so the row
               axis and product search that shape the grid do not narrow it. */
            <FulfilmentBoardListView
              contributions={allContributions}
              draft={draft}
              onDecide={decide}
              isLoading={board.isFetching}
            />
          ) : (
            <>
              {/* How much of the board is on screen. Only while a filter is on, and stated as
                  a fraction, so a narrowed board is never mistaken for the whole one. */}
              {filtering && (
                <p className="text-sm text-muted-foreground tabular-nums">
                  {`${visibleProductRows.length} of ${axis.rows.length} ${ROW_AXIS_NOUNS[rowAxis]}`}
                </p>
              )}

              {visibleProductRows.length === 0 ? (
                <Card>
                  <CardContent className="px-6 py-10 text-center">
                    <PackageSearch className="mx-auto size-6 text-muted-foreground" aria-hidden />
                    {/* NOT the "owes nothing" copy: the selection owes plenty, the filter
                        simply matched none of it. */}
                    <h3 className="mt-2 text-sm font-semibold">No products match</h3>
                  </CardContent>
                </Card>
              ) : (
                <FulfilmentBoardMatrix
                  dateBuckets={board.data.dateBuckets}
                  rows={visibleProductRows}
                  rowHeader={
                    ROW_AXIS_OPTIONS.find((option) => option.value === rowAxis)?.label ?? 'Product'
                  }
                  cells={axis.cells}
                  decidedKeys={decidedKeys}
                  onOpenCell={(cell) => setOpenCell(cell)}
                />
              )}
            </>
          )}

          <Card>
            <CardHeader className="block">
              <h3 className="text-sm font-semibold">Commit</h3>
              {/* One hint, not a paragraph: what a press does and where the Buy rows go. The
                  destination is a link because the cross-project Order Inquiries page is where
                  purchasing picks up an adopted order's rows. */}
              <p className="mt-0.5 text-sm text-muted-foreground">
                One confirmation per sales order; confirmed Buy rows go to{' '}
                <Link
                  href="/project-sales/order-inquiries"
                  className="text-primary hover:underline"
                >
                  Order Inquiries
                </Link>
                .
              </p>
            </CardHeader>
            <CardContent className="space-y-2">
              {standings.map((standing) => (
                <OrderCommitRow
                  key={standing.sales_order_id}
                  standing={standing}
                  preview={previews[standing.sales_order_id]}
                  busy={confirming === standing.sales_order_id}
                  refused={refusals[standing.sales_order_id] ?? []}
                  unpostable={unpostable[standing.sales_order_id] ?? []}
                  onConfirm={() => void confirmOrder(standing)}
                />
              ))}
            </CardContent>
          </Card>
        </>
      )}

      {liveCell && (
        <BoardCellBreakdownDialog
          cell={liveCell}
          bucketLabel={bucketLabel.get(liveCell.bucket_key) ?? liveCell.bucket_key}
          draft={draft}
          onDecide={decide}
          onClose={() => setOpenCell(null)}
        />
      )}

      {/* Confirmation dialog per PRINCIPLES: an irreversible batch write states what it is
          about to do, in numbers, before it does it. */}
      <AlertDialog open={confirmAllOpen} onOpenChange={setConfirmAllOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {`Confirm ${approvalSummary.approved} decisions across ${approvalSummary.orderCount} orders?`}
            </AlertDialogTitle>
            <AlertDialogDescription>
              Each order writes on its own; one order refusing does not stop the rest.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => void runConfirmAll()}>Confirm</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

/**
 * One selected order's standing and its Confirm.
 *
 * The disabled Confirm always states its reason. A button that is off without saying why is
 * what makes a screen feel broken, and here the reason is the honest shape of the design: the
 * board decides by cell, the database commits by order, and until every line of an order has a
 * verdict there is nothing to commit.
 */
function OrderCommitRow({
  standing,
  preview,
  busy,
  refused,
  unpostable,
  onConfirm,
}: {
  standing: BoardOrderStanding;
  preview?: BoardCommitPreview;
  busy: boolean;
  /** The lines the server would not take, kept beside the order that owns them. */
  refused: SupplyFailingLine[];
  /** Decided lines this confirmation must omit, each with the reason it cannot carry it. */
  unpostable: UnpostableLine[];
  onConfirm: () => void;
}) {
  const committing = preview?.committing ?? 0;
  const leaving = preview?.leaving_undecided ?? 0;
  const blocked = preview?.blocked ?? 0;
  return (
    <div className="space-y-2 rounded-lg border border-border px-3 py-2.5">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="truncate text-sm font-medium tabular-nums">{standing.so_number}</div>
          <div
            className="truncate text-sm text-muted-foreground"
            title={standing.customer_name ?? ''}
          >
            {standing.customer_name || 'Customer not recorded'}
          </div>
        </div>
        <div className="flex flex-col items-start gap-1 sm:flex-row sm:items-center sm:gap-3">
          <span className="text-sm tabular-nums">
            {`${standing.decided_count} of ${standing.line_count} lines decided`}
          </span>
          {/* What this press would actually do, stated before it is pressed. The counter above
              is information; this is the consequence. */}
          <span className="min-w-0 text-sm text-muted-foreground break-words">
            {committing === 0
                ? standing.decided_count > 0
                  // Everything decided on this order is already confirmed. Saying "nothing
                  // decided yet" beside "2 of 23 lines decided" contradicts the line above it.
                  ? 'Nothing new to confirm on this order.'
                  : 'Nothing decided yet on this order.'
                : leaving === 0
                  ? `Confirms all ${committing}.`
                : `Confirms ${committing}, leaves ${leaving} undecided for reorder planning${
                    blocked > 0
                      ? ` (${blocked} of them need a location on the sales order)`
                      : ''
                  }.`}
          </span>
          <Button
            type="button"
            size="sm"
            disabled={committing === 0 || busy}
            onClick={onConfirm}
          >
            {/* "Confirm 0 lines" on an untouched order would be a button describing nothing.
                The count only appears once it means something. */}
            {committing > 0 && leaving > 0
              ? `Confirm ${committing} line${committing === 1 ? '' : 's'}`
              : 'Confirm this order'}
          </Button>
        </div>
      </div>

      {/* A line the planner decided that this confirmation cannot carry. Named, with why,
          because dropping it silently would tell them they committed something they did not -
          and the fix is somewhere else (another screen, or the editor), so they would have no
          way to find out. One sentence per reason, so the count on the button and this notice
          always describe the same lines. */}
      {UNPOSTABLE_REASONS.map((reason) => {
        const lines = unpostable.filter((entry) => entry.reason === reason);
        if (lines.length === 0) return null;
        return (
          <p key={reason} className="text-sm text-amber-700 break-words">
            {unpostableNotice(reason, lines)}
          </p>
        );
      })}

      {/* A refusal names the lines it refused and why, beside the work that produced them. The
          draft is untouched, so the planner fixes and presses again rather than starting over. */}
      {refused.length > 0 && (
        <ul className="space-y-0.5 rounded-md bg-destructive/5 px-2 py-1.5">
          {refused.map((line, index) => (
            <li
              key={`${line.line_no ?? 'order'}-${line.item_code ?? ''}-${index}`}
              className="text-sm text-destructive break-words"
            >
              {line.line_no
                ? `Line ${line.line_no}${line.item_code ? `, ${line.item_code}` : ''}: ${line.reason}`
                : line.reason}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const UNPOSTABLE_REASONS: UnpostableReason[] = [
  'no_mirror',
  'no_reserve_warehouse',
  'buy_reason_missing',
];

/** The sentence naming the lines this confirmation leaves out for one reason, and the fix. */
function unpostableNotice(reason: UnpostableReason, lines: UnpostableLine[]): string {
  const named = lines
    .map((entry) => `${entry.contribution.item_code} line ${entry.contribution.line_no}`)
    .join(', ');
  const one = lines.length === 1;
  const them = one ? 'it' : 'them';
  if (reason === 'no_mirror') {
    return `${named} ${one ? 'is' : 'are'} not on the planning record yet, so this confirmation leaves ${them} out. Re-sync the sales order to add ${them}.`;
  }
  if (reason === 'no_reserve_warehouse') {
    return `${named} ${one ? 'reserves' : 'reserve'} at a warehouse the board cannot address, so this confirmation leaves ${them} out. Amend ${them} to place the Reserve.`;
  }
  return `${named} ${one ? 'buys' : 'buy'} a discontinued product with no reason given, so this confirmation leaves ${them} out. Amend ${them} to give one.`;
}
