'use client';

import * as React from 'react';
import Link from 'next/link';
import { ColumnDef } from '@tanstack/react-table';
import { PackageSearch } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { formatDateInMalaysia } from '@/lib/helpers';
import { PanelDataGrid } from '../../_shared/components/PanelDataGrid';
import { useStockDetail } from '../../_shared/hooks/useFulfilmentPlanning';
import { fromMinor, toMinor } from '../../_shared/lib/supplyComposition';
import type {
  StockDocumentMatch,
  StockDonorMatch,
  StockJumpTarget,
} from '../../_shared/types/fulfilmentPlanning.types';

/**
 * "SPO 202609-0041" against a raw `202609-0041`, or a raw number that already carries its
 * own "SPO-" prefix against itself: the engine's sentence always names the document with a
 * leading "SPO" (`front_planning_engine._named`), the drill's own `spo_number` does not
 * always. Stripped and cased down on both sides so either shape matches the other.
 */
function normalizeSpoNumber(value: string | null | undefined): string {
  return (value ?? '')
    .trim()
    .toUpperCase()
    .replace(/^SPO[\s-]*/, '');
}

/**
 * What the numbers on one location row are made of - AutoCount's "Stock Status with Detail".
 *
 * The captain reads this position in AutoCount and then comes here, so the shape is theirs: the
 * documents that produce the position, and a total that adds back up to it. A detail view whose
 * total disagrees with the row above it is the one thing that would make somebody stop trusting
 * the board.
 *
 * It is a PANEL rather than a dialog because the captain asked for "expandable details instead
 * of clicking in": it renders inside the row it belongs to, so the position and its documents
 * are on screen together and closing it is the same press that opened it. It scrolls in a region
 * of its own - the live book tops out at 501 documents for one product at one location, and a
 * panel that grows without limit would push the rest of the dialog out of reach.
 *
 * Addressed by IDS. Two products on the live book share the item code `B2155-NL-BLUE`, so a
 * lookup by code would answer confidently about the wrong one.
 *
 * NO HEADING BLOCK (captain, 30 August 2026). "B2155-NL-BLUE · BRW-IB" and the word "Documents"
 * sat between the location row and the columns that explain it, saying what the row already
 * says. The column headers now start directly under the row.
 *
 * NO RANK COLUMN AND NO STATE COLUMN (R5, 27 August 2026). The rank was the captain's own
 * earlier ask and it is answered by the queue screen, which exists to explain a ranking; here
 * it competed with the question this list is for, which is what else is claiming this stock and
 * when it is wanted.
 *
 * TWO READINGS, ONE COMPONENT.
 *
 * - Under a BIN row: that bin's documents, plain, in delivery-date order. No balance, because
 *   a per-bin running balance would answer a question the engine never asks.
 * - Under a GROUP SUBTOTAL row (`group`): every bin of the ownership group merged, in the order
 *   the engine reads the dates, supply adding and demand subtracting, with the pile after each
 *   row. Step 1 of the ladder draws the GROUP's pile - a `BRW-IB` line is fed by `MWH-IB` stock
 *   - so the group is the only level at which "what was left when my line came round" is true.
 *   The asker's own line is marked and `My line` jumps to it.
 */
export function StockDocumentsPanel({
  productId,
  warehouseId,
  group,
  lineIds = [],
  donor,
  documentInfo,
  filterText,
  jumpTarget,
}: {
  productId: string;
  /** One bin. Omitted for a group read, where the set is the answer. */
  warehouseId?: string | null;
  /** The whole SET: the ownership-group suffix (`IB`), or `pools` for the site pools. */
  group?: string | null;
  /**
   * The cell's own contributing lines. Their rows are tagged "This line", so the planner can
   * see where their own claim sits among the documents ahead of and behind it.
   */
  lineIds?: string[];
  /** The donor the active suggestion names (AC-3.3/3.13). Badged "Donor" wherever it matches -
   * most panels hold none of it, and simply render nothing extra. */
  donor?: StockDonorMatch | null;
  /** The SPO the active suggestion names (AC-3.4). Badged "This document" wherever it matches. */
  documentInfo?: StockDocumentMatch | null;
  /** The sticky toolbar's search (AC-3.5): SO number, customer, agent. */
  filterText?: string;
  /** A jump `CellStockTable` raised. Only the panel holding the matching row acts on it. */
  jumpTarget?: StockJumpTarget | null;
}) {
  const detail = useStockDetail(productId, warehouseId ?? null, lineIds, group);
  const isGroup = Boolean(group);
  const panelRef = React.useRef<HTMLDivElement | null>(null);

  const rows = React.useMemo<StockDetailRow[]>(() => {
    const data = detail.data;
    if (!data) return [];
    const documents: StockDetailRow[] = [
      // Keyed by POSITION as well as by id: one sales order can stand behind this location on
      // several of its own lines, so `sales_order_id` alone is not unique and React logged a
      // duplicate-key error for every repeat (measured live at BRW-BB, which returns the same
      // order many times over).
      ...data.sales_orders.map((order, index) => ({
        key: `so-${index}-${order.sales_order_id}`,
        doc_type: 'S/O' as const,
        doc_no: order.so_number,
        sales_order_id: order.sales_order_id,
        party: order.customer_name ?? null,
        agent_code: order.agent_code ?? null,
        project_label: order.project_label ?? null,
        location: order.location ?? null,
        doc_date: order.doc_date ?? null,
        due_date: order.delivery_date ?? null,
        overdue_days: null,
        qty: order.so_qty,
        // A sales order takes stock away from the pile.
        delta: -toMinor(order.so_qty),
        balance: null,
        line_id: order.line_id ?? null,
        is_this_line: Boolean(order.is_this_line),
        // AC-3.3/3.13: the donor the active suggestion named, by its own core line id where
        // the suggestion carried one - two lines of one donor SO would otherwise both light
        // up - falling back to the SO number for the shapes that only carry that.
        is_donor: Boolean(
          donor &&
          (donor.lineId
            ? order.line_id === donor.lineId
            : order.so_number === donor.soNumber),
        ),
        is_document: false,
      })),
      ...data.incoming.map((leg, index) => ({
        key: `spo-${index}-${leg.spo_number}`,
        doc_type: 'SPO' as const,
        doc_no: leg.spo_number,
        sales_order_id: null,
        party: leg.supplier_name ?? null,
        agent_code: null,
        project_label: null,
        location: leg.location ?? null,
        doc_date: null,
        due_date: leg.expected_date ?? null,
        overdue_days: leg.overdue_days ?? null,
        qty: leg.spo_qty,
        delta: toMinor(leg.spo_qty),
        balance: null,
        line_id: null,
        is_this_line: false,
        is_donor: false,
        // AC-3.4: the SPO the active suggestion named. Normalised on both sides - the
        // engine's sentence always says "SPO ...", the drill's own number does not always.
        is_document: Boolean(
          documentInfo &&
          normalizeSpoNumber(leg.spo_number) ===
            normalizeSpoNumber(documentInfo.spoNumber),
        ),
      })),
    ];
    if (!isGroup) return documents;

    // A confirmed hold taken by a line booked OUTSIDE this set (R40, 30 August 2026).
    // Cross-group stock moves only as a pinned hold, and such a hold is in no sales-order
    // row of this group - so a walk without it counts a pile nobody can draw on.
    documents.push(
      ...(data.holds ?? []).map((hold, index) => ({
        key: `hold-${index}-${hold.so_number ?? 'unnamed'}`,
        doc_type: 'Hold' as const,
        doc_no: hold.so_number ?? '-',
        sales_order_id: null,
        party: null,
        agent_code: null,
        project_label: null,
        location: hold.location ?? null,
        doc_date: null,
        due_date: hold.required_date ?? null,
        overdue_days: null,
        qty: hold.qty,
        delta: -toMinor(hold.qty),
        balance: null,
        line_id: null,
        is_this_line: false,
        is_donor: false,
        is_document: false,
      })),
    );

    // The pile each bin starts from, first and in bin order: the walk has to open on stock
    // somebody can actually pick, or the first balance would be a number out of nowhere.
    const opening: StockDetailRow[] = (data.bins ?? [])
      .filter((bin) => toMinor(bin.qty_on_hand) !== 0)
      .map((bin) => ({
        key: `on-hand-${bin.warehouse_id}`,
        doc_type: 'On hand' as const,
        // No document, and the Bin column already names the location: printing the code
        // here as well would be the same fact twice on one row.
        doc_no: '-',
        sales_order_id: null,
        party: null,
        agent_code: null,
        project_label: null,
        location: bin.location,
        doc_date: null,
        due_date: null,
        overdue_days: null,
        qty: bin.qty_on_hand,
        delta: toMinor(bin.qty_on_hand),
        balance: null,
        line_id: null,
        is_this_line: false,
        is_donor: false,
        is_document: false,
      }));

    documents.sort(compareByEngineDate);
    let running = 0;
    return [...opening, ...documents].map((row) => {
      running += row.delta;
      return { ...row, balance: fromMinor(running) };
    });
  }, [detail.data, isGroup, donor, documentInfo]);

  /**
   * The rows the sticky toolbar's search leaves standing (AC-3.5): SO number, customer or
   * agent, case-insensitively, client-side - the same rows the position above already holds,
   * never a second fetch. Applied AFTER the group walk builds the running balance, so a
   * filtered ledger keeps the balance each visible row actually landed on rather than one
   * recomputed over a narrower list.
   */
  const visibleRows = React.useMemo(() => {
    const needle = (filterText ?? '').trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter((row) =>
      [row.doc_no, row.party, row.agent_code]
        .filter((value): value is string => Boolean(value))
        .some((value) => value.toLowerCase().includes(needle)),
    );
  }, [rows, filterText]);

  const hasMyLine = visibleRows.some((row) => row.is_this_line);

  // The jump (AC-3.1/3.3/3.4): scroll to and briefly flash whichever row this panel holds
  // that the target names. Every open panel gets the same signal broadcast down from
  // `CellStockTable` and only the one holding a match does anything - the alternative is
  // addressing a jump to a panel that has not been told it is the one that matters, which
  // this component cannot know from outside the query it owns.
  React.useEffect(() => {
    if (!jumpTarget || detail.isLoading) return;
    const testId =
      jumpTarget.kind === 'this-line'
        ? 'stock-document-this-line'
        : jumpTarget.kind === 'donor'
          ? 'stock-document-donor'
          : 'stock-document-this-document';
    const anchor = panelRef.current?.querySelector(`[data-testid="${testId}"]`);
    const row = anchor?.closest('tr');
    if (!row) return;
    if (typeof row.scrollIntoView === 'function')
      row.scrollIntoView({ block: 'center' });
    // A single fading pulse, never a persistent second selection colour (AC-3.11) - the CSS
    // class collapses to a flat, briefer highlight under `prefers-reduced-motion` (styles.css).
    row.classList.add('jump-flash');
    const timer = window.setTimeout(
      () => row.classList.remove('jump-flash'),
      1500,
    );
    return () => window.clearTimeout(timer);
    // `visibleRows` re-runs the jump once the row it targets actually lands.
  }, [jumpTarget, detail.isLoading, visibleRows]);

  const columns = React.useMemo<ColumnDef<StockDetailRow>[]>(() => {
    const list: ColumnDef<StockDetailRow>[] = [
      {
        id: 'doc_type',
        accessorFn: (row) => row.doc_type,
        header: ({ column }) => (
          <DataGridColumnHeader title="Type" column={column} />
        ),
        cell: ({ row }) => (
          <span className={cn('text-sm font-medium', emphasis(row.original))}>
            {row.original.doc_type}
          </span>
        ),
        // Labels the totals row under the first column, the way a spreadsheet labels its sum.
        footer: () => <span className="text-muted-foreground">Total</span>,
        size: 90,
        minSize: 70,
        meta: { headerTitle: 'Type' },
      },
      {
        id: 'doc_no',
        accessorFn: (row) => row.doc_no,
        header: ({ column }) => (
          <DataGridColumnHeader title="Document" column={column} />
        ),
        cell: ({ row }) => (
          <span className="flex min-w-0 items-center gap-1.5">
            {row.original.sales_order_id ? (
              <Link
                href={`/scm/sales-orders/${row.original.sales_order_id}`}
                className={cn(
                  'truncate text-sm font-medium text-primary hover:underline',
                  emphasis(row.original),
                )}
                title={row.original.doc_no}
              >
                {row.original.doc_no}
              </Link>
            ) : (
              <span
                className={cn(
                  'truncate text-sm font-medium',
                  emphasis(row.original),
                )}
                title={row.original.doc_no}
              >
                {row.original.doc_no}
              </span>
            )}
            {/* The line the drawer was opened for. Without it a planner reading twenty
                documents cannot see which claim is theirs - and it is what `My line`
                scrolls to. */}
            {row.original.is_this_line ? (
              <span
                data-testid="stock-document-this-line"
                className="shrink-0 rounded bg-primary/10 px-1 text-[10px] font-medium text-primary"
              >
                This line
              </span>
            ) : null}
            {/* AC-3.3/3.13: the order the suggestion is borrowing FROM. Coexists with "This
                line" (AC-3.3) - a donor could in principle be a different line of the same
                order this drawer was opened for. */}
            {row.original.is_donor ? (
              <span
                data-testid="stock-document-donor"
                className="shrink-0 rounded bg-amber-500/10 px-1 text-[10px] font-medium text-amber-700 dark:text-amber-400"
              >
                Donor
              </span>
            ) : null}
            {/* AC-3.4: the SPO the suggestion is borrowing/using. */}
            {row.original.is_document ? (
              <span
                data-testid="stock-document-this-document"
                className="shrink-0 rounded bg-emerald-500/10 px-1 text-[10px] font-medium text-emerald-700 dark:text-emerald-400"
              >
                This document
              </span>
            ) : null}
          </span>
        ),
        size: 200,
        minSize: 150,
        meta: { headerTitle: 'Document' },
      },
      {
        id: 'party',
        accessorFn: (row) => row.party ?? '',
        header: ({ column }) => (
          <DataGridColumnHeader title="Customer / supplier" column={column} />
        ),
        cell: ({ row }) => (
          <span
            className={cn('block truncate text-sm', emphasis(row.original))}
            title={row.original.party ?? ''}
          >
            {row.original.party ||
              (row.original.doc_type === 'S/O' ||
              row.original.doc_type === 'SPO'
                ? 'Not recorded'
                : '-')}
          </span>
        ),
        size: 200,
        minSize: 150,
        meta: { headerTitle: 'Customer / supplier' },
      },
      {
        // Who sold it. A purchase row has no agent - it is not a sales document - so this
        // reads "-" there rather than a guess.
        id: 'agent_code',
        accessorFn: (row) => row.agent_code ?? '',
        header: ({ column }) => (
          <DataGridColumnHeader title="Agent" column={column} />
        ),
        cell: ({ row }) => (
          <span
            className={cn(
              'block truncate text-sm tabular-nums',
              emphasis(row.original),
            )}
          >
            {row.original.agent_code ?? '-'}
          </span>
        ),
        size: 100,
        minSize: 80,
        meta: { headerTitle: 'Agent' },
      },
    ];

    // NOT on the group reading: the walk is ordered by the date the stock is WANTED or
    // LANDS, and the day a document was typed plays no part in it. Leaving it in pushed
    // `Balance after` off the right edge of the dialog at 1280, which is the one column the
    // group reading exists for.
    if (!isGroup) {
      list.push({
        id: 'doc_date',
        accessorFn: (row) => row.doc_date ?? '',
        header: ({ column }) => (
          <DataGridColumnHeader title="Doc date" column={column} />
        ),
        cell: ({ row }) => (
          <span
            className={cn(
              'block truncate text-sm tabular-nums',
              emphasis(row.original),
            )}
          >
            {row.original.doc_date
              ? formatDateInMalaysia(row.original.doc_date)
              : 'Not stated'}
          </span>
        ),
        size: 120,
        minSize: 100,
        meta: { headerTitle: 'Doc date' },
      });
    }

    list.push({
      id: 'due_date',
      accessorFn: (row) => row.due_date ?? '',
      header: ({ column }) => (
        <DataGridColumnHeader title="Delivery / expected" column={column} />
      ),
      cell: ({ row }) => (
        <span
          className={cn(
            'block truncate text-sm tabular-nums',
            emphasis(row.original),
          )}
        >
          {row.original.due_date
            ? formatDateInMalaysia(row.original.due_date)
            : row.original.doc_type === 'On hand'
              ? 'Held now'
              : 'Not stated'}
          {row.original.overdue_days ? (
            <span className="text-amber-600 ms-1">
              (overdue {row.original.overdue_days}{' '}
              {row.original.overdue_days === 1 ? 'day' : 'days'})
            </span>
          ) : null}
        </span>
      ),
      size: 150,
      minSize: 120,
      meta: { headerTitle: 'Delivery / expected' },
    });

    if (isGroup) {
      // WHERE in the group each document sits. The whole point of the group reading is that
      // the pile is shared across the bins, so the bin has to stay visible per row.
      list.push({
        id: 'location',
        accessorFn: (row) => row.location ?? '',
        header: ({ column }) => (
          <DataGridColumnHeader title="Bin" column={column} />
        ),
        cell: ({ row }) => (
          <span
            className={cn('block truncate text-sm', emphasis(row.original))}
            title={row.original.location ?? ''}
          >
            {row.original.location ?? '-'}
          </span>
        ),
        size: 110,
        minSize: 90,
        meta: { headerTitle: 'Bin' },
      });
    }

    list.push({
      id: 'qty',
      accessorFn: (row) => Number(row.qty || 0),
      header: ({ column }) => (
        <DataGridColumnHeader title="Quantity" column={column} />
      ),
      cell: ({ row }) => (
        <span
          className={cn(
            'block truncate text-sm tabular-nums',
            emphasis(row.original),
          )}
        >
          {row.original.qty}
        </span>
      ),
      // Per TYPE, because an S/O subtracts where an SPO adds: one blended total would be a
      // number that matches nothing in the header above it.
      footer: () => (
        <span className="tabular-nums">
          {fromMinor(
            rows
              .filter((row) => row.doc_type === 'S/O')
              .reduce((total, row) => total + toMinor(row.qty), 0),
          )}
        </span>
      ),
      size: 120,
      minSize: 90,
      meta: { headerTitle: 'Quantity' },
    });

    if (isGroup) {
      list.push({
        id: 'balance',
        accessorFn: (row) => Number(row.balance || 0),
        header: ({ column }) => (
          <DataGridColumnHeader title="Balance after" column={column} />
        ),
        cell: ({ row }) => (
          <span
            data-testid={`stock-balance-${row.original.key}`}
            className={cn(
              'block truncate text-sm tabular-nums',
              emphasis(row.original),
              isNegative(row.original.balance) && 'text-destructive',
            )}
          >
            {row.original.balance}
          </span>
        ),
        // Where the group ends up once every row has been read. It is the subtotal's own
        // Available less two things the subtotal does not carry, both of them rows in this
        // list: THIS cell's own demand (the subtotal adds it back, because a line does not
        // compete with itself) and any hold taken from outside the group.
        footer: () => {
          const closing =
            rows.length > 0 ? rows[rows.length - 1].balance : null;
          return (
            <span
              className={cn(
                'tabular-nums',
                isNegative(closing) && 'text-destructive',
              )}
            >
              {closing ?? '-'}
            </span>
          );
        },
        size: 130,
        minSize: 110,
        meta: { headerTitle: 'Balance after' },
      });
    }

    return list;
  }, [isGroup, rows]);

  return (
    <div
      ref={panelRef}
      data-testid="stock-documents-panel"
      // Deliberately shorter than the stock table's own 50vh container, so the documents are
      // what scrolls rather than the position above them: measured at an 800px window, a taller
      // panel left the contributing lines a two-row sliver.
      className="max-h-[35vh] space-y-2 overflow-y-auto bg-muted/30 p-3"
    >
      {detail.isError ? (
        <p className="py-6 text-center text-sm text-destructive">
          {detail.error instanceof Error
            ? detail.error.message
            : 'The stock detail could not be loaded.'}
        </p>
      ) : detail.isLoading ? (
        <div data-testid="stock-documents-loading" className="space-y-2 py-2">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      ) : rows.length === 0 ? (
        <div className="py-8 text-center">
          <PackageSearch
            className="mx-auto size-6 text-muted-foreground"
            aria-hidden
          />
          <h3 className="mt-2 text-sm font-semibold">
            Nothing is claiming this stock
          </h3>
        </div>
      ) : visibleRows.length === 0 ? (
        // AC-3.5: a search that matches nothing is a DIFFERENT answer from "nothing is
        // claiming this stock" - the position still holds every row above, the search just
        // named none of them.
        <div
          data-testid="stock-documents-search-empty"
          className="py-8 text-center"
        >
          <PackageSearch
            className="mx-auto size-6 text-muted-foreground"
            aria-hidden
          />
          <h3 className="mt-2 text-sm font-semibold">
            No document matches your search
          </h3>
        </div>
      ) : (
        <PanelDataGrid<StockDetailRow>
          columns={columns}
          rows={visibleRows}
          getRowId={(row) => row.key}
          listingKey={
            isGroup
              ? 'projects.projects.view::project-stock-detail-group'
              : 'projects.projects.view::project-stock-detail'
          }
          // The group reading is a RUNNING balance, so its order is the arithmetic: re-sorting
          // it by customer would leave a column of numbers that add up to nothing.
          sortable={!isGroup}
          toolbar={
            isGroup && hasMyLine ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                data-testid="stock-documents-my-line"
                onClick={() => {
                  const anchor = panelRef.current?.querySelector(
                    '[data-testid="stock-document-this-line"]',
                  );
                  const row = anchor?.closest('tr');
                  if (row && typeof row.scrollIntoView === 'function') {
                    row.scrollIntoView({ block: 'center' });
                  }
                }}
              >
                My line
              </Button>
            ) : undefined
          }
          emptyTitle="Nothing is claiming this stock"
          // The live book tops out at 501 rows for one product and location, which is one page:
          // paging it would hide the total that makes the header checkable.
          pageSize={1000}
        />
      )}
    </div>
  );
}

/**
 * The order the ENGINE reads these documents in: on hand first (it is held now), then by the
 * date it is wanted or lands on, supply before demand on a tie - the ordering
 * `supply_assignment` walks, so a container cleared in the morning covers a despatch due the
 * same day. A document with no date lists last: "not stated" is not "wanted immediately".
 */
function compareByEngineDate(
  left: StockDetailRow,
  right: StockDetailRow,
): number {
  const leftDate = left.due_date ?? '';
  const rightDate = right.due_date ?? '';
  if (!leftDate !== !rightDate) return leftDate ? -1 : 1;
  if (leftDate !== rightDate) return leftDate < rightDate ? -1 : 1;
  const leftSupply = left.delta >= 0 ? 0 : 1;
  const rightSupply = right.delta >= 0 ? 0 : 1;
  if (leftSupply !== rightSupply) return leftSupply - rightSupply;
  return left.doc_no.localeCompare(right.doc_no);
}

/** The board's own row emphasis for the line the drawer was opened for. */
function emphasis(row: StockDetailRow): string {
  return row.is_this_line ? 'font-semibold text-primary' : '';
}

function isNegative(value: string | null): boolean {
  return value !== null && Number(value) < 0;
}

interface StockDetailRow {
  key: string;
  doc_type: 'S/O' | 'SPO' | 'On hand' | 'Hold';
  doc_no: string;
  sales_order_id: string | null;
  party: string | null;
  agent_code: string | null;
  project_label: string | null;
  /** The bin this row sits at. Columned only on the group reading. */
  location: string | null;
  doc_date: string | null;
  due_date: string | null;
  /** Days late, on a purchase document whose promised arrival has passed. */
  overdue_days: number | null;
  qty: string;
  /** Signed minor units: supply adds to the pile, demand takes from it. */
  delta: number;
  /** The pile after this row, on the group reading. Null on the per-bin one. */
  balance: string | null;
  line_id: string | null;
  /** One of the lines this drawer is planning (R5). */
  is_this_line: boolean;
  /** The order the active suggestion is borrowing from (AC-3.3/3.13). */
  is_donor: boolean;
  /** The SPO the active suggestion is borrowing/using (AC-3.4). */
  is_document: boolean;
}
