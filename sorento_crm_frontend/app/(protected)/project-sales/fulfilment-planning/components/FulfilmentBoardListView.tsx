'use client';

import * as React from 'react';
import Link from 'next/link';
import {
  ChevronDown,
  ChevronRight,
  ChevronsDownUp,
  ChevronsUpDown,
  PackageSearch,
} from 'lucide-react';
import { ColumnDef, RowSelectionState } from '@tanstack/react-table';
import { formatDateInMalaysia } from '@/lib/helpers';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { buildSelectColumn } from '@/components/ui/data-grid-select-column';
import { PanelDataGrid } from '@/components/common/PanelDataGrid';
import { BoardCellBreakdownDialog } from './BoardCellBreakdownDialog';
import { BoardDecidedMarker, decidedRevisions } from './BoardDecidedMarker';
import {
  BoardDecisionPill,
  VERDICT_SORT_RANK,
  verdictOf,
} from './BoardDecisionPill';
import { BoardVerdictActions } from './BoardVerdictActions';
import { BoardLineDecisionPanel } from './BoardLineDecisionPanel';
import { UnsavedDecisionPrompt, useDecisionRowExpansion } from './decisionRowExpansion';
import { BoardChangeTable } from './BoardChangeTable';
import { changedFieldsOf, lineKeyOf } from '../../_shared/lib/boardChangeAnnotations';
import type { BoardChangeAnnotation } from '../../_shared/lib/boardChangeAnnotations';
import { canQuickSave } from '../../_shared/lib/boardAmend';
import { contributionMatchesSearch } from '../../_shared/lib/fulfilmentBoard';
import {
  boardOrderInquiryWord,
  contributionDecision,
  contributionInquiryDecision,
  contributionSuggestion,
  // Aliased the way `SalesOrderDetail` aliases it: bare `describe` is vitest's, and a file
  // that imports both reads as though the test runner were writing the column.
  describe as describeSupply,
} from '../../_shared/lib/supplyVocabulary';
import type { SupplyPart } from '../../_shared/lib/supplyVocabulary';
import type {
  BoardCell,
  BoardContribution,
  BoardDecision,
  BoardDraft,
} from '../../_shared/types/fulfilmentPlanning.types';

/**
 * A single-line CELL, built from the contribution itself (`PLAN-oi-request-cs-reserve.md`
 * 3.9, AC-RS-42): the list view has no grid-axis cell to point at (the row IS the line), so
 * this wraps the line's own `locations` - the SAME per-location stock position the grid's
 * cell carries for it - in the shape `BoardCellBreakdownDialog` already renders, unchanged.
 * `bucket_key` is the contribution's own key: unique per row, and never read as a real date
 * bucket by the dialog (it only uses it as half of a remount key and a fallback label).
 */
function boardCellForContribution(contribution: BoardContribution): BoardCell {
  return {
    item_code: contribution.item_code,
    bucket_key: contribution.key,
    total_qty: contribution.qty_outstanding ?? contribution.qty,
    locations: contribution.locations ?? [],
    contributions: [contribution],
    unplannable_count: contribution.unplannable ? 1 : 0,
    contested_count: contribution.contested ? 1 : 0,
  };
}

/**
 * The board as a LIST, not a grid: one row per contributing line across every cell (D2,
 * PLAN-demo-followups-19aug-ladder-v2 "a list view of the board so Approve all can be seen
 * from an overview").
 *
 * The captain's ask was to see the whole draft at once - the grid answers "what does this
 * product owe by this date", the list answers "what is about to be committed, across every
 * order, in one scan". Same draft, same `onDecide`, same write path (there is none here
 * either - see `FulfilmentBoardPanel`'s own note): this is a second READING of the identical
 * data, never a second source of it.
 */
export function FulfilmentBoardListView({
  contributions,
  draft,
  onDecide,
  onDecideMany,
  annotations,
  externalSearch,
  pageResetKey,
  focusKey,
  onFocusHandled,
  poolSharePct,
}: {
  contributions: BoardContribution[];
  draft: BoardDraft;
  onDecide: (key: string, decision: BoardDecision | null) => Promise<boolean> | void;
  /**
   * D15: the quiet-bulk path the board-wide "Save all suggested" and this view's own header
   * button both post through, so several rows saved together toast once ("N lines saved · M
   * to confirm") rather than the N separate "Line N saved" toasts D14 shipped with.
   */
  onDecideMany: (keys: string[]) => Promise<{ saved: number; failed: number }>;
  /**
   * What the re-uploaded book did to each line, keyed by planning line (AC-C9). The row
   * shows it as a hazard icon in the column that moved, and the lightbox behind the icon
   * says the rest - the same component the grid cell uses.
   */
  annotations?: Map<string, BoardChangeAnnotation[]>;
  /**
   * S6 (PLAN-scm-oi-worklist-excel-parity.md R-J): the board's ONE search box, beside the
   * title, drives Grid and List alike now - this filters `contributions` with it BEFORE
   * handing them to `PanelDataGrid`, and `PanelDataGrid` is never given its own `searchOf`
   * any more, so there is no second box to type into.
   */
  externalSearch?: string;
  /**
   * Resets `PanelDataGrid`'s page on a change - `externalSearch` on its own, unless the
   * caller narrows `contributions` by something else too (`FulfilmentBoardPanel`'s kind
   * filter, on top of its own search): that caller passes its OWN composite key instead,
   * since a `contributions` array that changed only because of THAT filter would otherwise
   * leave the reader on whatever page 3 now shows instead of the top of the new list.
   */
  pageResetKey?: string;
  /**
   * Board-confirm-left-out AC-5: the row the left-out banner's own link asked to see, opened
   * here and scrolled into view. The BOARD says which row; this view is the one that already
   * owns the expansion state, so it is the one that acts on it.
   */
  focusKey?: string | null;
  /** Fired once `focusKey` has been opened, so the caller can clear it for the next click. */
  onFocusHandled?: () => void;
  /**
   * The board's own `pool_share_pct` (LADDER v8, R-K), threaded through to the per-line
   * Stock dialog exactly as the grid's own cell dialog receives it - a line's `locations`
   * can carry a site-pool row as readily as a cell's can.
   */
  poolSharePct?: number;
}) {
  /**
   * AC-RS-42: the Stock button and the "To plan" figure both open the SAME dialog the grid
   * view's cell strip does, scoped to this one line - never a second table reinventing what
   * `BoardCellBreakdownDialog` already draws.
   */
  const [openContribution, setOpenContribution] = React.useState<BoardContribution | null>(
    null,
  );
  const openCell = React.useMemo(
    () => (openContribution ? boardCellForContribution(openContribution) : null),
    [openContribution],
  );

  /**
   * Which rows are open - the same STATE the cell breakdown keeps, and the same panel inside
   * it, opened as MANY at a time here (AC-C12: Expand all would mean nothing on a list that
   * closes each row as the next one opens). The list used to carry Approve / Amend / Reject buttons in its Verdict
   * column and open the amend MODAL over the board; a decision is taken in the row on both
   * readings now, or the two would teach different gestures for one act - including the
   * question asked before an unsaved composition is thrown away (C5).
   */
  // S6: the row filter itself, off the board's own search box - `contributionMatchesSearch`
  // is the SAME matcher `rowMatchesSearch` reads for the grid's rows, so the two views can
  // never disagree about what one search term narrows to.
  const filteredContributions = React.useMemo(
    () => contributions.filter((contribution) => contributionMatchesSearch(contribution, externalSearch ?? '')),
    [contributions, externalSearch],
  );

  const expansion = useDecisionRowExpansion({ multiple: true });
  const {
    expanded,
    setExpanded,
    openKeys,
    dirtySetterFor,
    requestRow,
    expandAll,
    requestCollapseAll,
  } = expansion;

  /** Which row the scroll below has already fired for, so a re-render does not repeat it. */
  const lastScrolledFocusKey = React.useRef<string | null>(null);

  /**
   * Board-confirm-left-out AC-5: opens `focusKey`'s row alongside whatever is already open
   * (the multi-open reading, so nothing already on screen is thrown away).
   */
  React.useEffect(() => {
    if (!focusKey) {
      lastScrolledFocusKey.current = null;
      return;
    }
    setExpanded((current) => {
      const record = typeof current === 'boolean' ? {} : current;
      if (record[focusKey]) return current;
      return { ...record, [focusKey]: true };
    });
  }, [focusKey, setExpanded]);

  /**
   * The scroll itself, once the row `focusKey` named is actually open (`openKeys`, not
   * `focusKey` alone): the effect above ASKS for it to expand, and the row does not exist in
   * the DOM until the render that follows that state change lands - this effect re-fires on
   * exactly that render, because `openKeys` is what changed. Guarded by the ref above, not by
   * clearing `focusKey` on the caller's side alone: a second click naming the SAME already-
   * open row has to scroll again, and this is what tells "still the same request" apart from
   * "asked for again".
   *
   * S3 (fix round 2, reviewer): the ref is set and `onFocusHandled` fired only once the QUERY
   * ACTUALLY FOUND A NODE, not merely once the row is "open" - `openKeys` says the row is
   * expanded, not that it is currently RENDERED, and a search still narrowing the list to
   * something else (B1 above) or a page still on its way to the right one both leave `open`
   * true with nothing in the DOM yet. Marking it done regardless left later renders - the
   * search settling, the page landing - with no signal left to scroll on. `filteredContributions`
   * is an explicit dependency for the same reason: `openKeys` alone does not change when the
   * ROWS do (a search settling, a fresher board read), so a miss on THAT account would
   * otherwise never get a second attempt.
   */
  React.useEffect(() => {
    if (!focusKey || !openKeys.includes(focusKey)) return;
    if (lastScrolledFocusKey.current === focusKey) return;
    const node = document.querySelector(`[data-testid="line-decision-${focusKey}"]`);
    if (!node) return;
    lastScrolledFocusKey.current = focusKey;
    node.scrollIntoView({ block: 'center' });
    onFocusHandled?.();
  }, [focusKey, openKeys, onFocusHandled, filteredContributions]);

  /**
   * D14 (the captain: a quick save for the lines that need nothing amended). Selection is
   * the SAME `RowSelectionState` `BoardCellBreakdownDialog` keeps for its own bulk verbs -
   * ticked here, applied with `suggestedDecisionFor`, cleared once applied. A row that is
   * already covered or already carries a draft is not offered a box at all (`buildSelectColumn`
   * below): there is nothing a quick save would change on either.
   */
  const [rowSelection, setRowSelection] = React.useState<RowSelectionState>({});
  const selectedKeys = React.useMemo(
    () => Object.keys(rowSelection).filter((key) => rowSelection[key]),
    [rowSelection],
  );
  const saveSelectedAsSuggested = React.useCallback(() => {
    void onDecideMany(selectedKeys);
    setRowSelection({});
  }, [selectedKeys, onDecideMany]);

  /**
   * Open this line's decision panel, and only open it (AC-B10): the pencil is not a toggle -
   * a planner who presses it on a row that is already open asked to see the panel, and
   * closing it under them would read as the press having missed. `requestRow` still runs the
   * unsaved-work question on the way (the list opens many at once, so opening a second row
   * throws nothing away and asks nothing).
   */
  const openRow = React.useCallback(
    (key: string) => {
      if (openKeys.includes(key)) return;
      requestRow(key);
    },
    [openKeys, requestRow],
  );

  /**
   * The change icon this row shows in this column, or nothing (AC-C9).
   *
   * The column is read off what MOVED, through the same `changedFieldsOf` the lightbox
   * prints, so a date icon can never sit on a row whose date did not move. A line the book
   * touched without moving its quantity or its date still has a composed suggestion to
   * read, and that is what the Suggested column's icon is for.
   */
  const changeIcons = React.useCallback(
    (
      contribution: BoardContribution,
      column: 'required_date' | 'outstanding' | 'suggested',
    ) => {
      // The planning line first, then the sales order and line number - the address a row on
      // an order nobody has adopted carries instead (R3).
      const lineId = contribution.project_line_id;
      const forLine =
        (lineId ? annotations?.get(lineId) : undefined) ??
        annotations?.get(lineKeyOf(contribution.so_number, contribution.line_no)) ??
        [];
      const filtered = forLine.filter((annotation) => {
        const keys = changedFieldsOf(annotation).map((field) => field.key);
        if (column === 'required_date') return keys.includes('date');
        if (column === 'outstanding') return keys.includes('qty');
        return !keys.includes('date') && !keys.includes('qty');
      });
      if (filtered.length === 0) return null;
      // ONE icon per column, however many pending batch rows moved it (AC-D5, owner finding
      // 22 Sep: "why so many warning signs"). Two rows that each moved this line's date used
      // to draw two identical triangles side by side in one cell, which reads as two
      // problems; the lightbox behind the single icon lists them all instead.
      return (
        <BoardChangeTable
          key={`${filtered[0].rowId}-${column}`}
          annotations={filtered}
          column={column}
          compact
        />
      );
    },
    [annotations],
  );

  const columns = React.useMemo<ColumnDef<BoardContribution>[]>(
    () => [
      // The repo's own select column (the users list uses the same one), so a quick save is
      // a bulk action like any other rather than a second selection mechanism.
      buildSelectColumn<BoardContribution>({
        enableRow: (row) => canQuickSave(row.original, draft),
        disabledReason: (row) =>
          row.original.covered
            ? 'This line is already confirmed. Amend it to change what was decided.'
            : row.original.unplannable
              ? 'This line cannot be decided here: its sales order states no fulfilment location.'
              : draft[row.original.key]
                ? 'Already saved. Undo it before saving it again.'
                : undefined,
        rowLabel: (row) => `Select ${row.original.so_number} line ${row.original.line_no}`,
      }),
      // S6 (`PLAN-board-oi-mechanical-22sep.md`, AC-B6-13): the leftmost column, split out
      // of the "Sales order" cell's own `(Line N)` suffix below - AutoCount's own line
      // number, sortable on its own. The rows already ARRIVE in this order (`orderListRows`,
      // `FulfilmentBoardPanel`'s own `listContributions`), so no `sorting` state is seeded
      // here - the caller's own order IS the default (`PanelDataGrid`'s own contract).
      {
        id: 'line',
        accessorFn: (row) => row.line_no,
        header: ({ column }) => <DataGridColumnHeader title="Line" column={column} />,
        cell: ({ row }) => (
          <span className="block tabular-nums">{row.original.line_no}</span>
        ),
        size: 70,
        minSize: 60,
        enableSorting: true,
      },
      {
        id: 'so_number',
        accessorFn: (row) => row.so_number,
        header: ({ column }) => <DataGridColumnHeader title="Sales order" column={column} />,
        cell: ({ row }) => {
          const contribution = row.original;
          const body = (
            <div className="min-w-0">
              <div className="flex min-w-0 items-center gap-1.5">
                {/* A state indicator, not a control: the whole row opens the decision. */}
                {row.getIsExpanded() ? (
                  <ChevronDown
                    className="size-3.5 shrink-0 text-muted-foreground"
                    aria-hidden
                  />
                ) : (
                  <ChevronRight
                    className="size-3.5 shrink-0 text-muted-foreground"
                    aria-hidden
                  />
                )}
                {/* S6 (AC-B6-13/AC-B6-14): the number ONLY now - the line it carried
                    (AC-C13) moved into its own leftmost column above, so repeating it here
                    would say it twice on the same row. */}
                <span
                  className="truncate text-sm font-medium tabular-nums"
                  title={contribution.so_number}
                >
                  {contribution.so_number}
                </span>
                {/* The same tick the grid puts on a fully-decided cell, here per row: one
                    row IS one contribution, so it is decided or it is not. */}
                <BoardDecidedMarker
                  revisions={decidedRevisions([contribution])}
                />
              </div>
            </div>
          );
          // S6 (AC-B6-3/AC-B6-14): lands on this exact line of the sales order's own Lines
          // tab. `line_id` is already the CORE sales-order line id (its own doc comment,
          // `fulfilmentPlanning.types.ts`) - no backend change needed for this one.
          const href = contribution.sales_order_id
            ? `/scm/sales-orders/${contribution.sales_order_id}${
                contribution.line_id ? `?tab=lines&line=${contribution.line_id}` : ''
              }`
            : null;
          return href ? (
            <Link
              href={href}
              onClick={(event) => event.stopPropagation()}
              className="block min-w-0 hover:underline"
            >
              {body}
            </Link>
          ) : (
            body
          );
        },
        size: 150,
        minSize: 120,
        // Owner ruling, 22 Sep 2026: every column on this list sorts.
        enableSorting: true,
        meta: {
          // The SAME editor the cell breakdown expands, so a decision reads and is taken
          // identically whichever way the planner came at the line - the per-location
          // Available included (C4). The figures ride on the CONTRIBUTION, netted of this
          // line's own quantity, so the list does not have to know which cell the line sits
          // in to quote the right pile.
          expandedContent: (contribution: BoardContribution) =>
            // A cancelled line has no decision to take (R3): the book removed it, and
            // Confirm retires it. The row still opens, and says that rather than offering
            // controls that would compose supply for a quantity nobody is owed.
            contribution.cancelled ? (
              <p className="px-4 py-3 text-sm text-muted-foreground">
                This line was removed from the sales order. Confirm retires it; there is
                nothing left to decide for it.
              </p>
            ) : (
              <BoardLineDecisionPanel
                contribution={contribution}
                decision={draft[contribution.key] ?? null}
                locations={contribution.locations ?? []}
                onDecide={(next) => onDecide(contribution.key, next)}
                onDirtyChange={dirtySetterFor(contribution.key)}
              />
            ),
        },
      },
      {
        id: 'agent',
        accessorFn: (row) => row.agent_code ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Agent" column={column} />,
        cell: ({ row }) =>
          row.original.agent_code ? (
            <span
              className="block truncate tabular-nums"
              title={row.original.agent_label ?? row.original.agent_code}
            >
              {row.original.agent_code}
            </span>
          ) : (
            <span className="text-muted-foreground">Not stated</span>
          ),
        size: 110,
        minSize: 90,
        enableSorting: true,
      },
      {
        id: 'customer',
        accessorFn: (row) => row.customer_name ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Customer" column={column} />,
        cell: ({ row }) =>
          row.original.customer_name ? (
            <span className="block truncate" title={row.original.customer_name}>
              {row.original.customer_name}
            </span>
          ) : (
            <span className="text-muted-foreground">Not recorded</span>
          ),
        size: 180,
        minSize: 130,
        enableSorting: true,
      },
      {
        id: 'product',
        accessorFn: (row) => row.item_code,
        header: ({ column }) => <DataGridColumnHeader title="Product" column={column} />,
        cell: ({ row }) => {
          // AC-RL-06 amended (17 Sep, "beside the PRODUCT"), and the whole ladder since
          // AC-A1 to AC-A7: ONE word for how far this line's own inquiry has got, on every
          // line regardless of verdict, draft or decision - see `boardOrderInquiryWord`'s
          // own note for why this reads the inquiry directly rather than through the
          // Decided cell's gated `contributionInquiryDecision`.
          const word = boardOrderInquiryWord(row.original.order_inquiry);
          return (
            <span className="flex min-w-0 items-center gap-1.5">
              <span
                className="block min-w-0 truncate tabular-nums"
                title={row.original.item_code}
              >
                {row.original.item_code}
              </span>
              {word ? (
                <Badge
                  size="sm"
                  appearance="light"
                  variant="secondary"
                  className="shrink-0"
                  // AC-A3 to AC-A5, R1: the chip is a WORD, and the document number(s) or
                  // the inquiry's own number ride in the tooltip - there is no room for
                  // either beside a product code at 375px.
                  title={word.title}
                >
                  {word.word}
                </Badge>
              ) : null}
            </span>
          );
        },
        size: 140,
        minSize: 110,
        enableSorting: true,
      },
      // S6 (AC-B6-15): the live OI row this line raised, linking straight to it. A line
      // with no live row - nothing raised, or the row it raised has since settled/gone -
      // reads a plain dash, never a guess.
      {
        id: 'order_inquiry',
        accessorFn: (row) => row.order_inquiry?.inquiry_no ?? '',
        header: ({ column }) => <DataGridColumnHeader title="OI" column={column} />,
        cell: ({ row }) => {
          const inquiry = row.original.order_inquiry;
          if (!inquiry?.inquiry_no) return <span className="text-muted-foreground">-</span>;
          // A row whose payload carries neither id - one raised before inquiries were
          // numbered, or a header the join could not reach - is plain text rather than a
          // link that lands nowhere in particular.
          const href =
            inquiry.inquiry_id && inquiry.row_id
              ? `/project-sales/order-inquiries/${inquiry.inquiry_id}?row=${inquiry.row_id}`
              : null;
          if (!href) {
            return (
              <span className="block truncate tabular-nums" title={inquiry.inquiry_no}>
                {inquiry.inquiry_no}
              </span>
            );
          }
          return (
            <Link
              href={href}
              onClick={(event) => event.stopPropagation()}
              className="block truncate tabular-nums text-primary hover:underline"
              title={inquiry.inquiry_no}
            >
              {inquiry.inquiry_no}
            </Link>
          );
        },
        size: 120,
        minSize: 100,
        enableSorting: true,
      },
      {
        id: 'required_date',
        accessorFn: (row) => row.required_date ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Required date" column={column} />,
        cell: ({ row }) => (
          <span className="flex min-w-0 items-center gap-1">
            {row.original.required_date ? (
              <span className="block min-w-0 truncate tabular-nums">
                {formatDateInMalaysia(row.original.required_date)}
              </span>
            ) : (
              <span className="text-muted-foreground">No date</span>
            )}
            {changeIcons(row.original, 'required_date')}
          </span>
        ),
        size: 130,
        minSize: 110,
        enableSorting: true,
      },
      {
        id: 'owed_qty',
        // Numeric, not the raw string `qty_outstanding`/`qty` ride on - a lexicographic
        // sort would put "20" ahead of "9" (owner ruling, 22 Sep 2026).
        accessorFn: (row) => Number(row.qty_outstanding ?? row.qty ?? 0),
        // "To plan", not "Outstanding qty" - the 14 Sep 2026 ruling's own word for this
        // figure (the cell dialog's own subtitle already reads "N to plan"), and the word
        // AC-RS-42 names for the figure this column now also opens the Stock dialog from.
        header: 'To plan',
        cell: ({ row }) => {
          const contribution = row.original;
          return (
            <span className="flex min-w-0 items-center gap-1">
              <button
                type="button"
                className="block min-w-0 truncate text-start tabular-nums hover:underline"
                data-testid={`board-list-to-plan-${contribution.key}`}
                onClick={(event) => {
                  event.stopPropagation();
                  setOpenContribution(contribution);
                }}
              >
                {contribution.qty_outstanding ?? contribution.qty}
              </button>
              {changeIcons(contribution, 'outstanding')}
              {/* AC-RS-42: a labelled Stock button per row, opening the SAME dialog the
                  grid view's cell strip does - purchasing used to leave this screen and
                  open the grid just to check one line's own stock. */}
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-6 gap-1 px-1.5"
                aria-label="Stock"
                data-testid={`board-list-stock-${contribution.key}`}
                onClick={(event) => {
                  event.stopPropagation();
                  setOpenContribution(contribution);
                }}
              >
                <PackageSearch className="size-3.5" aria-hidden />
                <span className="hidden xl:inline">Stock</span>
              </Button>
            </span>
          );
        },
        size: 160,
        minSize: 140,
        enableSorting: true,
      },
      {
        // AC-D4: what the ENGINE said, in PLAN section 2's own words. Split off the old
        // single "Proposal" column, which showed the decision on a decided line and the
        // proposal on an undecided one - so the two could never be compared, which is the
        // one thing the planner opens this view to do.
        id: 'suggested',
        // Owner ruling, 22 Sep 2026: sorts on the SAME text the cell prints
        // (`suggestedSortText` below), so the sort order and the words on screen can never
        // disagree.
        accessorFn: (row) => suggestedSortText(row),
        header: ({ column }) => <DataGridColumnHeader title="Suggested" column={column} />,
        cell: ({ row }) => {
          const contribution = row.original;
          if (contribution.unplannable) {
            // The ladder was never walked for it (AC-FP16), so there is nothing to suggest -
            // and the reason is the one thing worth saying in its place.
            return (
              <span className="text-muted-foreground">Needs a location</span>
            );
          }
          const parts = contributionSuggestion(contribution);
          if (!parts) {
            // A decision frozen before the proposal was recorded. Not "nothing suggested".
            return <span className="text-muted-foreground">Not recorded</span>;
          }
          const text = describeSupply(parts, contribution.fulfilment_location);
          // NO BAR (AC-C13). The composition is already written out beside it in words, and
          // the bar cost the row a second text line to say the same thing less precisely.
          return (
            <span className="flex min-w-0 items-center gap-1.5">
              <span className="block min-w-0 truncate" title={text}>
                {text || (
                  <span className="text-muted-foreground">Nothing proposed</span>
                )}
              </span>
              {contribution.buy_origin === 'local' && hasBuy(parts) && (
                <Badge variant="secondary">Local</Badge>
              )}
              {changeIcons(contribution, 'suggested')}
            </span>
          );
        },
        size: 240,
        minSize: 170,
        enableSorting: true,
      },
      {
        id: 'decided',
        // Owner ruling, 22 Sep 2026: sorts on the SAME text the cell prints
        // (`decidedSortText` below).
        accessorFn: (row) => decidedSortText(row, draft[row.key] ?? null),
        header: ({ column }) => <DataGridColumnHeader title="Decided" column={column} />,
        cell: ({ row }) => {
          const contribution = row.original;
          const drafted = draft[contribution.key] ?? null;
          const parts = contributionDecision(contribution, drafted);
          if (!parts) {
            // DECIDED BY THE BOOK, not by a board (14 Sep 2026 ruling): a line carrying a
            // live order inquiry row has no composition to print, so the slot names the
            // instruction purchasing already holds. "Not decided" over it would invite a
            // second Buy for a line somebody has already been told to buy.
            const inquiry = contributionInquiryDecision(contribution);
            if (inquiry) {
              const text = inquiry.inquiry_no ?? 'Unnumbered inquiry';
              // AC-RL-06 amended (17 Sep review round), widened by AC-A7: the stage word -
              // `received` / `used` / `SPO` / `PO` / `OI` - sits beside the PRODUCT (this
              // row's own `product` column, driven by `boardOrderInquiryWord`) so it reads
              // on every line, not only the ones that land in this branch; printing it here
              // too would say it twice on a line that does.
              return (
                <span className="flex min-w-0 items-center gap-1 tabular-nums">
                  <span className="block min-w-0 truncate" title={text}>
                    {text}
                  </span>
                </span>
              );
            }
            return <span className="text-muted-foreground">Not decided</span>;
          }
          // The composition alone, in section 2's words. NOT "Confirmed rev 1 · Buy 43":
          // the revision is already on the Verdict column and on the row's tick, and
          // repeating it here would cost the width the composition needs. No bar either
          // (AC-C13) - the words carry it, and the grid still draws one where a cell has
          // the room.
          const text = describeSupply(parts, contribution.fulfilment_location);
          return (
            <span className="flex min-w-0 items-center gap-1.5">
              <span className="block min-w-0 truncate" title={text}>
                {text}
              </span>
              {contribution.buy_origin === 'local' && hasBuy(parts) && (
                <Badge variant="secondary">Local</Badge>
              )}
            </span>
          );
        },
        size: 240,
        minSize: 170,
        enableSorting: true,
      },
      {
        id: 'rank',
        accessorFn: (row) => row.rank_score,
        header: ({ column }) => <DataGridColumnHeader title="Rank" column={column} />,
        cell: ({ row }) =>
          row.original.covered || row.original.unplannable ? (
            <span className="text-muted-foreground">-</span>
          ) : (
            <span className="tabular-nums">
              {row.original.rank_score.toFixed(2)}
            </span>
          ),
        size: 80,
        minSize: 70,
        enableSorting: true,
      },
      {
        id: 'verdict',
        // AC-7: sorted by the SAME state the pill renders (`verdictOf`, `BoardDecisionPill`) -
        // never a second reading of "how far this line has got", which is exactly how the
        // column and the pill it sorts could come to disagree.
        accessorFn: (row) => VERDICT_SORT_RANK[verdictOf(row, draft[row.key] ?? null)],
        enableSorting: true,
        header: ({ column }) => <DataGridColumnHeader title="Verdict" column={column} />,
        // A PILL, and the row's own actions beside it (`BoardVerdictActions`, AC-B11): the
        // trio on a line the engine or the book still proposes, Undo on one something has
        // been written for, and Change decision on every line that has one to take. Shared
        // with the cell breakdown's Decision column so the two cannot drift.
        cell: ({ row }) => {
          const contribution = row.original;
          const key = contribution.key;
          return (
            <div className="flex min-w-0 items-center gap-1">
              <BoardDecisionPill contribution={contribution} decision={draft[key] ?? null} />
              <BoardVerdictActions
                contribution={contribution}
                decision={draft[key] ?? null}
                onDecide={(next) => onDecide(key, next)}
                onChange={() => openRow(key)}
              />
            </div>
          );
        },
        // AC-C1/AC-C2: wide enough for the pill and the three icons any one state offers
        // (Accept + Reject + Change decision, or Undo + Change decision), and RESIZABLE -
        // the column carried `enableResizing: false` while every other one on this grid
        // could be dragged, which read as the grid being broken on the one column a planner
        // acts in.
        size: 240,
        minSize: 170,
      },
    ],
    [changeIcons, dirtySetterFor, draft, onDecide, openRow, setOpenContribution],
  );

  return (
    <>
    <PanelDataGrid
      title="Every contributing line"
      columns={columns}
      rows={filteredContributions}
      getRowId={(row) => row.key}
      pageResetKey={pageResetKey ?? externalSearch}
      listingKey="projects.projects.view::project-fulfilment-board-list-v1"
      emptyTitle="Nothing is outstanding on this board"
      rowSelection={rowSelection}
      onRowSelectionChange={setRowSelection}
      enableRowSelection={(row) => canQuickSave(row.original, draft)}
      toolbar={
        <div className="flex flex-wrap items-center gap-2">
          {/* The same pair reorder planning carries, in the same place and the same shape
              (AC-C12): two icon buttons, each dead when it has nothing to do, so the
              control itself says whether the list is open or closed. */}
          <Button
            type="button"
            variant="outline"
            size="sm"
            mode="icon"
            className="h-8 w-8"
            data-testid="board-list-expand-all"
            title="Expand all"
            aria-label="Expand all"
            disabled={openKeys.length >= filteredContributions.length}
            onClick={() => expandAll(filteredContributions.map((row) => row.key))}
          >
            <ChevronsUpDown className="size-4" aria-hidden />
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            mode="icon"
            className="h-8 w-8"
            data-testid="board-list-collapse-all"
            title="Collapse all"
            aria-label="Collapse all"
            disabled={openKeys.length === 0}
            onClick={requestCollapseAll}
          >
            <ChevronsDownUp className="size-4" aria-hidden />
          </Button>
          {selectedKeys.length > 0 ? (
            <>
              <Badge variant="secondary" className="h-8 gap-1 px-2.5 text-sm">
                {`${selectedKeys.length} selected`}
              </Badge>
              <Button type="button" size="sm" onClick={saveSelectedAsSuggested}>
                {`Save as suggested (${selectedKeys.length})`}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => setRowSelection({})}
              >
                Clear
              </Button>
            </>
          ) : null}
        </div>
      }
      expanded={expanded}
      onExpandedChange={setExpanded}
      onRowClick={(row) => requestRow(row.key)}
      pageSize={25}
      // Owner ruling, 22 Sep 2026: every column on this list sorts.
      sortable
      // AC-5, fix round 1: the banner's link names a ROW, not a page - `PanelDataGrid` jumps
      // to whichever page currently holds it, in its own sorted order, so a left-out line
      // beyond page 1 is reachable rather than a dead link.
      focusRowId={focusKey}
    />
    <UnsavedDecisionPrompt state={expansion} />
    {/* AC-RS-42: the grid view's OWN dialog, unchanged, opened here for one line at a time -
        the expanded decision panel above is untouched. */}
    {openCell && (
      <BoardCellBreakdownDialog
        cell={openCell}
        bucketLabel={
          openContribution?.required_date
            ? formatDateInMalaysia(openContribution.required_date)
            : 'No date'
        }
        draft={draft}
        poolSharePct={poolSharePct}
        onDecide={onDecide}
        onDecideMany={onDecideMany}
        onClose={() => setOpenContribution(null)}
      />
    )}
    </>
  );
}

/** Whether a Buy actually contributed to this composition (S3, R-Local). */
function hasBuy(parts: SupplyPart[] | null): boolean {
  return Boolean(parts?.some((part) => part.kind === 'buy' && Number(part.qty) > 0));
}

/**
 * The plain text the Suggested column's cell prints, shared with its own `accessorFn`
 * (owner ruling, 22 Sep 2026: every column sorts) so the sort order can never disagree with
 * the words on screen.
 */
function suggestedSortText(contribution: BoardContribution): string {
  if (contribution.unplannable) return 'Needs a location';
  const parts = contributionSuggestion(contribution);
  if (!parts) return 'Not recorded';
  return describeSupply(parts, contribution.fulfilment_location) || 'Nothing proposed';
}

/** The Decided column's own equivalent of `suggestedSortText` above. */
function decidedSortText(contribution: BoardContribution, drafted: BoardDecision | null): string {
  const parts = contributionDecision(contribution, drafted);
  if (!parts) {
    const inquiry = contributionInquiryDecision(contribution);
    if (inquiry) return inquiry.inquiry_no ?? 'Unnumbered inquiry';
    return 'Not decided';
  }
  return describeSupply(parts, contribution.fulfilment_location);
}
