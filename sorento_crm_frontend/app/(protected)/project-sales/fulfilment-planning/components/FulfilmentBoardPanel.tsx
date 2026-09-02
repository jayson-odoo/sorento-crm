'use client';

import * as React from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { toast } from 'sonner';
import {
  ArrowLeft,
  LayoutGrid,
  List,
  PackageSearch,
  Settings,
  Undo2,
} from 'lucide-react';
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
import { Card, CardContent } from '@/components/ui/card';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import {
  useConfirmManyMutation,
  useFulfilmentPlanningMutations,
  useLineDraftMutation,
  usePlanningBoard,
} from '../../_shared/hooks/useFulfilmentPlanning';
import { usePlanningChangeBatch } from '../../_shared/hooks/usePlanningChanges';
import {
  annotationsByCell,
  preMarkedKeys,
  uncoverChangedLines,
} from '../../_shared/lib/boardChangeAnnotations';
import {
  boardAxis,
  bucketLabelText,
  confirmSummaryFor,
  orderByProductRows,
  rowMatchesSearch,
  confirmLinesFor,
  shiftedDayWindow,
  unpostableDecidedFor,
  type UnpostableLine,
  type UnpostableReason,
} from '../../_shared/lib/fulfilmentBoard';
import type {
  BoardCell,
  BoardContribution,
  BoardDecision,
  BoardDraft,
  BoardGranularity,
  BoardRowAxis,
  ConfirmManyOrderResult,
} from '../../_shared/types/fulfilmentPlanning.types';
import { BoardCellBreakdownDialog } from './BoardCellBreakdownDialog';
import { BoardTransfersPanel } from './BoardTransfersPanel';
import { FulfilmentBoardListView } from './FulfilmentBoardListView';
import { FulfilmentBoardMatrix } from './FulfilmentBoardMatrix';
import { DecisionStrip } from './DecisionStrip';
import { cellCarriesKind, contributionCarriesKind } from '../../_shared/lib/decisionStrip';
import type { SupplyKind } from '../../_shared/lib/supplyVocabulary';

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
  batchId,
  onBack,
}: {
  soNumbers: string[];
  /**
   * The planning-change batch the board was opened ON (`?batch=<id>`, AC-P3-1).
   *
   * Everything it changes is additive: the changed lines' cells carry a Was / Now table and
   * arrive pre-marked, and Confirm applies the batch instead of writing an ordinary revision.
   * A board opened without one is untouched.
   */
  batchId?: string | null;
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
  const {
    value: productSearchInput,
    setValue: setProductSearchInput,
    debouncedValue: productSearch,
  } = useDebouncedSearch(searchParams.get('product') ?? '');
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
  /**
   * The decision-strip card currently narrowing the grid, or null (AC-D2).
   *
   * Deliberately NOT in the URL, unlike the dials above: it is a way of reading the board in
   * front of you while you work, not a state of the board worth sending to somebody else, and
   * a shared link that arrived pre-filtered would hide the rest of the plan without saying so.
   */
  const [kindFilter, setKindFilter] = React.useState<SupplyKind | null>(null);
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

  /**
   * The batch the board was opened on (AC-P3-1). Undefined `batchId` fetches nothing.
   *
   * Read beside the board rather than folded into it: the board is a live read of what is
   * outstanding and the batch is a record of what an upload did, and one payload carrying
   * both would have the board refuse to render whenever the batch could not be loaded.
   */
  const changeBatch = usePlanningChangeBatch(batchId ?? undefined);

  const rawBoard = usePlanningBoard(
    soNumbers,
    granularity,
    // Always the LIVE policy. The preview was a what-if for showing a fair weighting before one
    // was switched on; the fair policy is now the live one, the offer was retired with it, and
    // the banner that carried the way back went with the banner itself.
    false,
    dayWindow ? { dayWindow } : {},
  );

  /**
   * The board as the CHANGED lines make it: a line the book has moved is no longer covered
   * by the decision taken for it, so it arrives undecided carrying the batch's own fresh
   * proposal (`uncoverChangedLines`). Identity on every board opened without a batch.
   */
  const changeBatchData = changeBatch.data ?? null;
  const board = React.useMemo(
    () => ({
      ...rawBoard,
      data: rawBoard.data
        ? uncoverChangedLines(rawBoard.data, changeBatchData)
        : rawBoard.data,
    }),
    [rawBoard, changeBatchData],
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

  const { adopt } = useFulfilmentPlanningMutations();
  const { save: saveLineDraft, remove: removeLineDraft } = useLineDraftMutation();

  // NO PER-ORDER CONFIRM (R11). The board used to carry one Confirm per sales order in a
  // Commit section under the matrix, each with its own busy flag and its own refusal list.
  // A planner reading a board of nine orders had nine buttons to press to say one thing, and
  // the refusals were three screens below the rows that caused them. There is ONE Confirm
  // now, in the header bar, and it posts every order in one call.

  // NO PER-ORDER LEDGER. It accumulated which order each contribution key belonged to across
  // every day window the planner had scrolled through, so the per-order "N of M lines decided"
  // counter would not fall as they moved. That counter went with the Commit section (R13), and
  // the one counter left is summed over the whole selection, unwindowed, from `contributions`.

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
   * Every changed line of the batch arrives PRE-MARKED (AC-P3-3).
   *
   * Seeded into the board's own DRAFT, not into a second state: the cell then colours, counts
   * and confirms exactly as a line the planner ticked themselves, and un-ticking one is the
   * same gesture it always was. Once, on the first board that carries both the batch and its
   * lines - re-seeding on every render would put back a tick the planner had just cleared.
   *
   * A verdict the planner has already given is never overwritten.
   */
  const preMarked = React.useRef(false);
  React.useEffect(() => {
    if (!batchId || preMarked.current) return;
    if (!changeBatchData || allContributions.length === 0) return;
    const keys = preMarkedKeys(changeBatchData, allContributions);
    if (keys.length === 0) return;
    preMarked.current = true;
    setDraft((current) => {
      const next = { ...current };
      for (const key of keys) if (!next[key]) next[key] = { verdict: 'approved' };
      return next;
    });
  }, [batchId, changeBatchData, allContributions]);

  /**
   * A line SAVED elsewhere - another device, another planner, or this one before a reload -
   * arrives ON THE BOARD ITSELF (S4, R-F): `contribution.draft` is the server's own row, and
   * this seeds it into the SAME `draft` map a click here would write, so a Saved pill, the
   * header counter and Confirm all read the one state whichever way the line got there.
   *
   * Seeded on EVERY board read, not once like `preMarked` above: AC-4.5 ("a second planner
   * sees the first planner's saved lines") needs a later fetch to bring in a save nobody
   * here made. `!next[key]` is what keeps this from clobbering THIS session's own edit - the
   * same guard `preMarked` uses, and for the same reason: a verdict already given here is
   * never overwritten by what the server happened to say a moment before.
   */
  React.useEffect(() => {
    const serverDrafts = allContributions.filter((contribution) => contribution.draft);
    if (serverDrafts.length === 0) return;
    setDraft((current) => {
      let changed = false;
      const next = { ...current };
      for (const contribution of serverDrafts) {
        if (!next[contribution.key] && contribution.draft) {
          next[contribution.key] = contribution.draft.decision;
          changed = true;
        }
      }
      return changed ? next : current;
    });
  }, [allContributions]);

  /**
   * Save decision / Undo (S4, R-F): local first, then the server write, so the pill answers
   * the click before any network round-trip - and reverted, with the mutation's own error
   * toast, if the write fails.
   *
   * Reads `draft` and `allContributions` off the closure rather than through `setDraft`'s
   * updater: `decide` is recreated every render `draft` changes, so a click always runs the
   * FRESHEST closure, and the toast below needs a plain, synchronous "the draft as it now
   * stands" to compute `confirmSummaryFor` against - a value `setDraft`'s own updater cannot
   * hand back synchronously (React does not promise WHEN it runs).
   */
  const decide = React.useCallback(
    async (key: string, decision: BoardDecision | null) => {
      const previous = draft;
      const next = { ...draft };
      if (decision) next[key] = decision;
      else delete next[key];
      setDraft(next);
      try {
        if (decision) {
          const contribution = allContributions.find((entry) => entry.key === key);
          // The suggestion this decision was taken against travels with it: the server
          // keeps it as the snapshot `draft.stale` is judged against on every later read
          // (AC-4.4). The SAVER is read off the caller's own JWT, never sent from here.
          await saveLineDraft(key, decision, contribution?.proposed);
        } else {
          await removeLineDraft(key);
        }
      } catch {
        // The mutation's own `onError` already toasted the message; nothing here is left to
        // say beyond putting the board back the way the click found it.
        setDraft(previous);
        return;
      }
      if (decision && decision.verdict !== 'rejected') {
        const contribution = allContributions.find((entry) => entry.key === key);
        const { toConfirm } = confirmSummaryFor(allContributions, next);
        toast.success(
          `Line ${contribution?.line_no ?? ''} saved · ${toConfirm} to confirm`,
        );
      }
    },
    [draft, allContributions, saveLineDraft, removeLineDraft],
  );

  /**
   * The same lines, in the GRID's product order.
   *
   * The two views are two readings of one payload and the reader toggles between them to find
   * the same line; the grid's axis is `productRows` and the list was showing the demand query's
   * own order, so the same product sat in two places and the toggle became a re-search. One
   * ordering, the payload's, applied here rather than inside the list so `allContributions` -
   * which Approve-all and the confirm dialog also read - keeps the order the server served in.
   *
   * On a PIVOTED axis the grid's rows are sales orders, customers or projects, so there is no
   * product sequence to agree with; the list is the overview of the whole selection either way
   * and keeps the product order, which is the axis it has a column for.
   */
  const listContributions = React.useMemo<BoardContribution[]>(
    () => orderByProductRows(allContributions, board.data?.productRows ?? []),
    [allContributions, board.data],
  );

  /**
   * What one press of Confirm would do: "N to confirm · M rejected" (D1/D3).
   *
   * Counted over exactly the population `confirmLinesFor` posts, so the sentence beside the
   * button and what the button does can never disagree. `confirmSummaryFor` is the shared
   * implementation (`_shared/lib/fulfilmentBoard.ts`) - `decide()`'s own S4 save toast needs
   * the SAME count read off the draft it just wrote, before this `useMemo` has re-run with
   * it, so the reduction lives in one place rather than being kept in step by hand in two.
   */
  const confirmSummary = React.useMemo(
    () => confirmSummaryFor(allContributions, draft),
    [allContributions, draft],
  );

  /**
   * Decided lines this confirmation cannot carry, across the WHOLE board, each with why.
   *
   * It used to sit inside the per-order commit card that R13 removed. Named rather than
   * dropped in silence: the fix is somewhere else (another screen, or the row's own editor),
   * so a planner told nothing would have no way to find out they had not committed it.
   */
  const unpostable = React.useMemo<UnpostableLine[]>(() => {
    if (!board.data) return [];
    const contributions = board.data.contributions;
    return board.data.orders.flatMap((order) =>
      unpostableDecidedFor(
        contributions,
        order.sales_order_id,
        draft,
        Boolean(order.project_sales_order_id),
      ),
    );
  }, [board.data, draft]);

  /**
   * Why Confirm is off, when it is (AC-P3-4).
   *
   * BOARD-WIDE now that there is one Confirm. It was per order while every order had its own
   * button; with one press applying the whole batch, the only question left is whether that
   * batch has already been applied. Stated rather than left as a dead button, and the server
   * refuses the same case, so the screen and the write cannot disagree.
   */
  const batchApplied = changeBatch.data?.applied_at ?? null;
  /**
   * The sales orders whose OWN batch rows have all been applied already.
   *
   * One upload moves many orders and the batch itself only reads applied once the last of
   * them is written, so an order that has already had its change applied would otherwise be
   * posted a second time by the next press - writing another revision of a change that is
   * already in the plan. It is left out of the body and said so in the result, rather than
   * blocking the whole board: the other orders on it still have a change nobody has decided.
   */
  const appliedSoNumbers = React.useMemo(() => {
    const out = new Set<string>();
    for (const order of changeBatchData?.orders ?? []) {
      if (order.rows.length > 0 && order.rows.every((row) => row.applied_state === 'applied')) {
        out.add(order.so_number);
      }
    }
    return out;
  }, [changeBatchData]);
  const confirmBlockedReason = React.useMemo<string | null>(() => {
    if (!batchApplied) return null;
    return `This planning change was applied ${formatDateTimeInMalaysia(batchApplied)}${
      changeBatch.data?.applied_by_name ? ` by ${changeBatch.data.applied_by_name}` : ''
    }.`;
  }, [batchApplied, changeBatch.data?.applied_by_name]);

  const confirmMany = useConfirmManyMutation();
  const [confirmAllOpen, setConfirmAllOpen] = React.useState(false);
  /**
   * Undo all throws away every decision taken since the board was opened, and there is no way
   * back to them: it is destructive in the only sense a client draft can be, so it is
   * confirmed with the count first, like every other destructive verb in this product.
   */
  const [undoAllOpen, setUndoAllOpen] = React.useState(false);
  const [confirmingAll, setConfirmingAll] = React.useState(false);
  const [batchResults, setBatchResults] = React.useState<ConfirmManyOrderResult[] | null>(null);

  /**
   * CONFIRM (R11): one call, grouped per order, each order writing in its OWN transaction
   * server-side (`confirm_many`) - so one order's refusal never takes the others down. Any
   * order that has not been adopted yet is adopted first; the board is re-read once
   * afterwards so the fresh mirror lines can be named in the payload (adoption fills
   * `project_line_id`, which is null until then).
   *
   * The population is `confirmLinesFor`'s own, which is the point of the ruling: a plannable
   * line nobody rejected is confirmed as suggested, whether or not the planner touched it.
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
            if (contribution.unplannable) return false;
            const decision = draft[contribution.key];
            if (decision?.verdict === 'rejected') return false;
            // Covered and untouched: the server carries it, so this press has nothing to
            // post for it and its order is not put in the batch on its account alone.
            if (contribution.covered && decision?.verdict !== 'amended') return false;
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
      // An order whose planning change is already applied is NOT sent again (AC-P3-4). It is
      // reported instead, in the same place a server refusal is reported, so a press that
      // deliberately skipped it does not read as a press that did nothing.
      const skipped: ConfirmManyOrderResult[] = [];
      for (const salesOrderId of wantedOrders) {
        const psoId = psoIdBySalesOrder.get(salesOrderId);
        if (!psoId) continue;
        const soNumber = liveBoard.orders.find(
          (order) => order.sales_order_id === salesOrderId,
        )?.so_number;
        if (soNumber && appliedSoNumbers.has(soNumber)) {
          skipped.push({
            pso_id: psoId,
            ok: false,
            error: 'This planning change was already applied to this sales order.',
          } as ConfirmManyOrderResult);
          continue;
        }
        const lines = confirmLinesFor(contributions, salesOrderId, draft);
        if (lines.length > 0) orders.push({ pso_id: psoId, lines });
      }
      if (orders.length === 0) {
        if (skipped.length > 0) setBatchResults(skipped);
        return;
      }

      // The batch the board was opened on travels with the press (AC-P3-4). Without it a
      // Confirm on a `?batch=` board writes an ordinary revision and leaves the planning
      // change pending for ever - the per-order Confirm carried it before this button
      // replaced the per-order cards.
      const result = await confirmMany.mutateAsync(
        batchId ? { orders, batch_id: batchId } : { orders },
      );
      setBatchResults([...skipped, ...result.results]);

      // What the press produced, in the three numbers a planner is about to act on (D3):
      // the promises made, the movements somebody now has to approve (the panel below lists
      // them), and the rows purchasing has been handed.
      const ok = result.results.filter((entry) => entry.ok);
      const linesConfirmed = orders
        .filter((order) => ok.some((entry) => entry.pso_id === order.pso_id))
        .reduce((total, order) => total + order.lines.length, 0);
      const transfers = ok.reduce((total, entry) => total + (entry.transfers_written ?? 0), 0);
      // What was already on a warehouse's list and stayed there (R16). Said only when there
      // IS one: on a first confirmation it is always zero, and a zero in the sentence would
      // be a number the reader has to decide to ignore.
      const kept = ok.reduce((total, entry) => total + (entry.transfers_kept ?? 0), 0);
      const inquiries = ok.reduce((total, entry) => total + (entry.inquiry_rows_created ?? 0), 0);
      if (ok.length > 0) {
        toast.success(
          `${linesConfirmed} line${linesConfirmed === 1 ? '' : 's'} confirmed · ` +
            `${transfers} transfer${transfers === 1 ? '' : 's'} proposed · ` +
            (kept > 0 ? `${kept} kept · ` : '') +
            `${inquiries} inquiry row${inquiries === 1 ? '' : 's'}`,
        );
      }

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
  }, [board, allContributions, draft, adopt, confirmMany, batchId, appliedSoNumbers]);

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

  /**
   * What the re-uploaded book did to each cell's lines (AC-P3-2), keyed as the matrix keys
   * its cells. Empty on every board opened without a batch.
   */
  const changeAnnotations = React.useMemo(
    () => annotationsByCell(changeBatchData, axis.cells),
    [changeBatchData, axis],
  );

  /**
   * What the decision strip is summed over: THE LINES THE CURRENT VIEW CAN SHOW.
   *
   * The grid renders cells, and at day granularity those are a 30-day window; the list renders
   * the whole selection. Summing the strip over the selection while filtering the grid over
   * its cells let a card read "Shared 71" off lines three months out and then empty the board
   * when it was pressed - a figure the view cannot produce, acted on. So the population
   * follows the view, and the card and the figures above it can never disagree.
   */
  const stripContributions = React.useMemo<BoardContribution[]>(() => {
    if (view === 'list') return listContributions;
    // Keyed, because a pivoted axis regroups the same cells and a line must not be counted
    // twice for landing in two of them.
    const seen = new Map<string, BoardContribution>();
    for (const cell of axis.cells) {
      for (const contribution of cell.contributions) seen.set(contribution.key, contribution);
    }
    return [...seen.values()];
  }, [view, listContributions, axis]);

  /**
   * The cells a decision-strip card leaves on screen (AC-D2): the ones carrying that kind on
   * EITHER side, suggested or decided.
   *
   * A filter over the axis's own cells, so the rows follow: a row every one of whose cells is
   * filtered out drops out with them, and the "N of M" fraction below counts it.
   */
  const visibleCells = React.useMemo(
    () =>
      kindFilter
        ? axis.cells.filter((cell) => cellCarriesKind(cell, draft, kindFilter))
        : axis.cells,
    [axis, draft, kindFilter],
  );

  /** The same card, obeyed by the list. Both views answer to one press or neither should. */
  const visibleListContributions = React.useMemo(
    () =>
      kindFilter
        ? listContributions.filter((contribution) =>
            contributionCarriesKind(contribution, draft[contribution.key] ?? null, kindFilter),
          )
        : listContributions,
    [listContributions, draft, kindFilter],
  );

  /** Lines per row, so the search can ask whether ANY of a row's lines matches. */
  const linesByRow = React.useMemo(() => {
    const map = new Map<string, BoardContribution[]>();
    for (const cell of visibleCells) {
      const key = cell.row_key ?? cell.item_code;
      const held = map.get(key);
      if (held) held.push(...cell.contributions);
      else map.set(key, [...cell.contributions]);
    }
    return map;
  }, [visibleCells]);

  const visibleProductRows = React.useMemo(
    () =>
      axis.rows.filter(
        (row) =>
          (!kindFilter || linesByRow.has(row.key)) &&
          rowMatchesSearch(row, linesByRow.get(row.key) ?? [], productSearch),
      ),
    [axis, linesByRow, productSearch, kindFilter],
  );

  const filtering = productSearch.trim().length > 0 || kindFilter !== null;

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
        <ListSearchInput
          value={productSearchInput}
          onChange={setProductSearchInput}
          placeholder="Search sales order, customer, project or product"
          aria-label="Search sales order, customer, project or product"
          className="w-full sm:w-64"
        />

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
          {/* NO "Back to sales orders" HERE. It lives under the gear on the bar below (R12):
              this row is the controls that decide what the board SHOWS, and a way off the
              screen sitting among them competed with them for the same glance. */}
        </div>
      </div>

      {/* THE ONE ACTION BAR (D1). Its own row above the grid/list so it is visible whichever
          view is on screen. What it says on the left is what the button on the right will
          do, counted over the same population, and the order is fixed: the gear (the rare
          things) then Confirm, last on the right, where a primary action belongs.
          The gear renders EVEN WHILE THE BOARD IS STILL LOADING or has come back empty: it
          is this screen's only way off it, since the header row deliberately carries none
          (the comment above it) - a board slow to load, or with nothing to plan, still needs
          an exit. Confirm and its counter stay gated on real data: there is nothing to
          confirm before there is a board. */}
      <div
        data-testid="board-action-bar"
        className="flex flex-col gap-2 rounded-lg border border-border px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between"
      >
        {board.data && board.data.cells.length > 0 ? (
          <span
            data-testid="board-confirm-summary"
            className="text-sm text-muted-foreground tabular-nums"
          >
            {`${confirmSummary.toConfirm} to confirm · ${confirmSummary.rejected} rejected`}
          </span>
        ) : (
          <span />
        )}
        <div className="flex flex-wrap items-center gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                size="sm"
                variant="outline"
                mode="icon"
                aria-label="Board actions"
              >
                <Settings className="size-4" aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {/* Every decision taken on this board since it was opened, or since the
                  last confirm, goes back to the suggestion - on the SERVER too (S4): each
                  key is deleted through `decide(key, null)`, or the next board read would
                  seed the discarded lines straight back in. Nothing CONFIRMED moves. */}
              <DropdownMenuItem
                disabled={Object.keys(draft).length === 0}
                onSelect={
                  Object.keys(draft).length === 0 ? undefined : () => setUndoAllOpen(true)
                }
              >
                <Undo2 className="size-4" aria-hidden />
                Undo all
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={onBack}>
                <ArrowLeft className="size-4" aria-hidden />
                Back to sales orders
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          {board.data && board.data.cells.length > 0 ? (
            <Button
              type="button"
              size="sm"
              data-testid="board-confirm"
              disabled={
                confirmSummary.toConfirm === 0 || confirmingAll || Boolean(confirmBlockedReason)
              }
              title={confirmBlockedReason ?? undefined}
              onClick={() => setConfirmAllOpen(true)}
            >
              {`Confirm (${confirmSummary.toConfirm})`}
            </Button>
          ) : null}
        </div>
      </div>

      {/* Why Confirm is off, when it is - stated, never a dead button. */}
      {confirmBlockedReason ? (
        <p data-testid="confirm-blocked" className="text-sm text-muted-foreground break-words">
          {confirmBlockedReason}
        </p>
      ) : null}

      {/* A line the planner decided that this confirmation cannot carry. Named, with why,
          because dropping it silently would tell them they committed something they did not,
          and the fix is somewhere else. One sentence per reason, so the count on the button
          and this notice always describe the same lines. */}
      {UNPOSTABLE_REASONS.flatMap((reason) => {
        const lines = unpostable.filter((entry) => entry.reason === reason);
        if (lines.length === 0) return [];
        return unpostableNotices(reason, lines).map((sentence, index) => (
          <p key={`${reason}-${index}`} className="text-sm text-amber-700 break-words">
            {sentence}
          </p>
        ));
      })}

      {batchResults && (
        <div
          data-testid="board-confirm-results"
          className="space-y-1 rounded-lg border border-border px-3 py-2.5"
        >
          <p className="text-sm font-medium">
            {`${batchResults.filter((r) => r.ok).length} of ${batchResults.length} orders confirmed`}
          </p>
          <ul className="space-y-1">
            {batchResults.map((result) => {
              const order = board.data?.orders.find(
                (candidate) => candidate.project_sales_order_id === result.pso_id,
              );
              const label = order?.so_number ?? result.pso_id;
              // A refusal names the LINES it refused, not just the order: the fix is on one
              // row, and "SO404352: refused" sends a planner to read thirty of them.
              const failing = result.failing_lines ?? [];
              return (
                <li key={result.pso_id} className="space-y-0.5">
                  <span
                    className={`block text-sm break-words ${result.ok ? 'text-emerald-700' : 'text-destructive'}`}
                  >
                    {result.ok
                      ? `${label}: confirmed as revision ${result.decision_revision} (${result.inquiry_rows_created ?? 0} purchase row${(result.inquiry_rows_created ?? 0) === 1 ? '' : 's'} handed over)`
                      : `${label}: ${result.error ?? 'refused'}`}
                  </span>
                  {failing.length > 0 && (
                    <ul className="space-y-0.5 rounded-md bg-destructive/5 px-2 py-1.5">
                      {failing.map((line, index) => (
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
                <h3 className="mt-2 text-sm font-semibold">Nothing is outstanding in these dates</h3>
                <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                  {`The selection holds ${board.data?.line_count} lines on other dates.`}
                </p>
              </>
            ) : (
              <>
                <h3 className="mt-2 text-sm font-semibold">
                  Nothing is outstanding on these sales orders that can be planned
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

          {/* NO "N of M lines are already past their delivery date" BANNER (retired 26
              August 2026, AC-C5). The column headers already say "Already past" over the
              periods it is talking about, so the banner restated the screen in words and
              pushed the grid down a row to do it. */}

          {/* NO POLICY BANNER. It named the rule and listed its weights across the top of the
              board, and the captain's verdict on it was "this text is not needed at the top":
              it is not what anybody opens this screen to read, and it was there whether or not
              a question about ranking had been asked. The information is not lost - the rank
              popover on a row names the policy above its factor table, which is where somebody
              IS asking - see `BoardRankPopover` and PLAN 13.10. */}

          {/* NO LEGEND ROW (retired 26 August 2026, AC-C5). The decision strip below carries
              every label in its own colour, so a legend was the same six words twice - and
              the one a reader meets first should be the one with the numbers on it. */}

          {/* Suggested vs decided across the selection, card per kind (AC-D2). */}
          <DecisionStrip
            contributions={stripContributions}
            draft={draft}
            active={kindFilter}
            onToggle={(kind) =>
              setKindFilter((current) => (current === kind ? null : kind))
            }
          />

          {/* The movements this board's confirmations raised, ABOVE the matrix (R13). They
              used to be reachable only from the transfers screen, so the promise was made
              here and the movement it implied was approved by somebody who had not seen the
              order it was for. */}
          <BoardTransfersPanel
            soNumbers={soNumbers}
            justConfirmed={batchResults !== null}
            inquiryRows={(batchResults ?? [])
              .filter((result) => result.ok)
              .reduce((total, result) => total + (result.inquiry_rows_created ?? 0), 0)}
          />

          {view === 'list' ? (
            /* D2: one row per contributing line across every cell of the WHOLE selection, not
               the pivoted/windowed rows the grid shows - the point is an overview, so the row
               axis and product search that shape the grid do not narrow it. */
            <FulfilmentBoardListView
              contributions={visibleListContributions}
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
                  cells={visibleCells}
                  draft={draft}
                  annotations={changeAnnotations}
                  onOpenCell={(cell) => setOpenCell(cell)}
                />
              )}
            </>
          )}

          {/* NO COMMIT SECTION (R13). It was one card per sales order carrying a Confirm,
              a "N of M lines decided" counter and a paragraph explaining where Buy rows and
              stock transfers go. The counter is the bar at the top, the Confirm is the one
              button beside it, and the two destinations are a panel of real transfers above
              and a link under it - facts rather than a description of them. */}
        </>
      )}

      {liveCell && (
        <BoardCellBreakdownDialog
          cell={liveCell}
          bucketLabel={bucketLabel.get(liveCell.bucket_key) ?? liveCell.bucket_key}
          draft={draft}
          poolSharePct={board.data?.pool_share_pct}
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
              {`Confirm ${confirmSummary.toConfirm} line${
                confirmSummary.toConfirm === 1 ? '' : 's'
              } across ${confirmSummary.orderCount} order${
                confirmSummary.orderCount === 1 ? '' : 's'
              }?`}
            </AlertDialogTitle>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => void runConfirmAll()}>Confirm</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Undo all discards work nobody can get back. Same rule, same component. */}
      <AlertDialog open={undoAllOpen} onOpenChange={setUndoAllOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {`Discard ${Object.keys(draft).length} draft decision${
                Object.keys(draft).length === 1 ? '' : 's'
              }?`}
            </AlertDialogTitle>
            <AlertDialogDescription>
              Every line goes back to the suggestion. Nothing already confirmed changes.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep them</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                // S4/AC-4.3: a saved line's draft lives on the server now, so discarding it
                // has to be the SAME `decide(key, null)` a single line's own Undo takes - a
                // bare local `setDraft({})` cleared the screen and left every one of them to
                // re-seed right back in off the next board refetch.
                for (const key of Object.keys(draft)) void decide(key, null);
                setUndoAllOpen(false);
              }}
            >
              Discard
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

const UNPOSTABLE_REASONS: UnpostableReason[] = [
  'no_mirror',
  'no_reserve_warehouse',
  'buy_reason_missing',
];

/** How many names a sentence carries before it stops being a sentence and becomes a wall. */
const NAMED_CAP = 5;

/** What each reason IS, in the words the untouched-line count uses, for one line and for many. */
const UNPOSTABLE_SHORT: Record<UnpostableReason, [string, string]> = {
  no_mirror: ['is not on the planning record yet', 'are not on the planning record yet'],
  no_reserve_warehouse: [
    'reserves at a warehouse the board cannot address',
    'reserve at a warehouse the board cannot address',
  ],
  buy_reason_missing: [
    'buys a discontinued product with no reason given',
    'buy a discontinued product with no reason given',
  ],
};

/**
 * The sentences naming what this confirmation leaves out for one reason, and the fix.
 *
 * TWO POPULATIONS, because they need different words (R11). A line the planner composed is
 * NAMED - they are looking for the one they just worked on - capped at five names, since a
 * list longer than that is scrolled past rather than read. Lines nobody touched are confirmed
 * as suggested and can be left out for the same reasons, and there can be hundreds of them, so
 * they are COUNTED and the reader is told where to go and decide them.
 */
export function unpostableNotices(
  reason: UnpostableReason,
  lines: UnpostableLine[],
): string[] {
  const out: string[] = [];
  const touched = lines.filter((entry) => entry.touched);
  const untouched = lines.length - touched.length;

  if (touched.length > 0) {
    const names = touched
      .slice(0, NAMED_CAP)
      .map((entry) => `${entry.contribution.item_code} line ${entry.contribution.line_no}`)
      .join(', ');
    const rest = touched.length - Math.min(touched.length, NAMED_CAP);
    const named = rest > 0 ? `${names} and ${rest} more` : names;
    const one = touched.length === 1;
    const them = one ? 'it' : 'them';
    if (reason === 'no_mirror') {
      out.push(
        `${named} ${one ? 'is' : 'are'} not on the planning record yet, so this confirmation leaves ${them} out. Re-sync the sales order to add ${them}.`,
      );
    } else if (reason === 'no_reserve_warehouse') {
      out.push(
        `${named} ${one ? 'reserves' : 'reserve'} at a warehouse the board cannot address, so this confirmation leaves ${them} out. Amend ${them} to place the Reserve.`,
      );
    } else {
      out.push(
        `${named} ${one ? 'buys' : 'buy'} a discontinued product with no reason given, so this confirmation leaves ${them} out. Amend ${them} to give one.`,
      );
    }
  }

  if (untouched > 0) {
    const one = untouched === 1;
    out.push(
      `${untouched} untouched line${one ? '' : 's'} ${UNPOSTABLE_SHORT[reason][one ? 0 : 1]}; open ${one ? 'it' : 'them'} to decide.`,
    );
  }

  return out;
}
