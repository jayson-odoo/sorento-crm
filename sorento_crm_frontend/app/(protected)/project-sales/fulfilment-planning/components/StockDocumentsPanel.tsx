'use client';

import * as React from 'react';
import Link from 'next/link';
import { ColumnDef } from '@tanstack/react-table';
import { PackageSearch } from 'lucide-react';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { formatDateInMalaysia } from '@/lib/helpers';
import { PanelDataGrid } from '../../_shared/components/PanelDataGrid';
import { useStockDetail } from '../../_shared/hooks/useFulfilmentPlanning';
import { fromMinor, toMinor } from '../../_shared/lib/supplyComposition';
import { availableForProject, POOLS_SET } from '../../_shared/lib/poolShare';
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
 * - Under the SITE POOL subtotal specifically (`group === 'pools'`), the running column reads
 *   "Available for Project" instead of "Balance after" - R-K, S2: the pool's own share of that
 *   running balance, never the raw pile, capped by the same five-pool net the summary row's
 *   own column is. An ownership group keeps the raw pile: there is no dealer share to keep
 *   back from `IB` or `BB`.
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
  /**
   * Every donor the active suggestion names (AC-3.3/3.13). Badged "Donor" on EVERY row of
   * this panel that matches ANY of them - a step-2 combine can draw from several donors on
   * one line (R35), and a list-of-one just badges the one it always did. Most panels hold
   * none of it, and simply render nothing extra.
   */
  donor?: StockDonorMatch[] | null;
  /** The SPO the active suggestion names (AC-3.4). Badged "This document" wherever it matches. */
  documentInfo?: StockDocumentMatch | null;
  /** The sticky toolbar's search (AC-3.5): SO number, customer, agent. */
  filterText?: string;
  /** A jump `CellStockTable` raised. Only the panel holding the matching row acts on it. */
  jumpTarget?: StockJumpTarget | null;
}) {
  const detail = useStockDetail(productId, warehouseId ?? null, lineIds, group);
  const isGroup = Boolean(group);
  /**
   * R-K, S2: under a SITE POOL section the running column is the pool's share, not the raw
   * pile - a GROUP section (`IB`, `BB`, ...) keeps plain `Balance after`, unchanged, because
   * there is no dealer share to keep back from an ownership group.
   */
  const isPoolsSection = group === POOLS_SET;
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
        assumed_date: null,
        counted: true,
        qty: order.so_qty,
        // A sales order takes stock away from the pile.
        delta: -toMinor(order.so_qty),
        balance: null,
        line_id: order.line_id ?? null,
        is_this_line: Boolean(order.is_this_line),
        // AC-3.3/3.13: the donor the active suggestion named, by its own core line id where
        // the suggestion carried one - two lines of one donor SO would otherwise both light
        // up - falling back to the SO number for the shapes that only carry that. EVERY
        // donor in the list gets a chance to match, not only the first (review round, S3) -
        // a step-2 combine can name several on one line (R35).
        is_donor: Boolean(
          donor?.some((match) =>
            match.lineId
              ? order.line_id === match.lineId
              : order.so_number === match.soNumber,
          ),
        ),
        is_document: false,
      })),
      ...data.incoming.map((leg, index) => {
        // R-O, review fix round S5: a document the walk counts as nothing (past the dead
        // line) still LISTS, labelled "Not counted" (`dateCellText`), but must not move
        // the balance - it is the row that says "the walk gave you nothing here", and a
        // delta from it would silently add supply the ladder itself refused.
        const counted = leg.counted !== false;
        return {
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
          assumed_date: leg.assumed_date ?? null,
          counted,
          qty: leg.spo_qty,
          delta: counted ? toMinor(leg.spo_qty) : 0,
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
        };
      }),
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
        assumed_date: null,
        counted: true,
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
        assumed_date: null,
        counted: true,
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

  /**
   * The jump's own watch state, held in a REF rather than closed over by the effect below
   * (review round, S3): the effect is keyed on `jumpTarget`'s own identity alone now, so a
   * still-pending MutationObserver from an EARLIER jump has to be reachable and disconnectable
   * from the start of a later run, not just from that earlier run's own cleanup.
   */
  const jumpWatchRef = React.useRef<{
    observer: MutationObserver | null;
    flashTimer: number | undefined;
  }>({ observer: null, flashTimer: undefined });

  // The jump (AC-3.1/3.3/3.4): scroll to and briefly flash whichever row this panel holds
  // that the target names. Every open panel gets the same signal broadcast down from
  // `CellStockTable` and only the one holding a match does anything - the alternative is
  // addressing a jump to a panel that has not been told it is the one that matters, which
  // this component cannot know from outside the query it owns.
  //
  // WAITS FOR THE ROW'S OWN NODE, not merely for `visibleRows` to hold data (AC-3.1 auto-land
  // fix, S3 bug-fix round). `PanelDataGrid` carries its OWN async gate - the shared listing's
  // column-preference fetch - so the tick where `detail.isLoading` turns false and this data
  // exists is NOT the tick the `<tr>` actually lands in `panelRef`'s subtree; measured live,
  // the auto-land on a cell's OWN mount fired against zero rows in the DOM (`rowCount: 113`
  // in this hook, `hasAnchor: false` in the grid) while the identical jump from the "My line"
  // button - pressed after that second render had already happened - found it immediately.
  // A `MutationObserver` reacts to the node actually arriving rather than to a timer or to
  // one extra assumed tick, so it is correct regardless of how many renders the grid needs -
  // including the render that only finishes loading AFTER this effect first runs, so
  // `detail.isLoading` is not read here at all: the observer keeps watching through it.
  //
  // DRIVEN OFF `jumpTarget`'s OWN IDENTITY ALONE (review round, S3 bug-fix). `visibleRows`
  // used to sit in this dependency list, on the reasoning that a filtered ledger should
  // re-arm the watch once its target actually exists. What it actually did: `donorMatch`/
  // `documentMatch` were built as fresh object literals in `BoardCellBreakdownDialog` on
  // every render, so `visibleRows` (built from `rows`, which closes over `donor`/
  // `documentInfo`) got a new identity on every keystroke of the STICKY SEARCH, even though
  // the search had not settled and the filtered set had not actually changed - which re-ran
  // this effect, found the SAME row already painted, and re-scrolled to and re-flashed it on
  // every keystroke. `jumpTarget` itself already only changes when a jump is actually
  // requested (`CellStockTable`'s `activeJump` state), so keying on it - and on nothing a
  // render can jostle - is what makes typing never scroll.
  React.useEffect(() => {
    if (!jumpTarget) return;
    const panel = panelRef.current;
    if (!panel) return;
    const testId =
      jumpTarget.kind === 'this-line'
        ? 'stock-document-this-line'
        : jumpTarget.kind === 'donor'
          ? 'stock-document-donor'
          : 'stock-document-this-document';

    const watch = jumpWatchRef.current;
    // A watch still pending from an earlier jump loses the race the moment a NEW one is
    // requested - only the jump just asked for gets to land.
    watch.observer?.disconnect();
    watch.observer = null;
    window.clearTimeout(watch.flashTimer);

    const findRow = (): HTMLElement | null => {
      const anchor = panel.querySelector(`[data-testid="${testId}"]`);
      return anchor?.closest('tr') ?? null;
    };

    const land = (row: HTMLElement) => {
      // Idempotent: nothing further to watch for once a row has actually landed.
      watch.observer?.disconnect();
      watch.observer = null;
      if (typeof row.scrollIntoView === 'function')
        row.scrollIntoView({ block: 'center' });
      // A single fading pulse, never a persistent second selection colour (AC-3.11) - the
      // CSS class is disabled outright under `prefers-reduced-motion` (styles.css).
      //
      // REMOVED BEFORE IT IS RE-ADDED, with a reflow forced in between (review round, S3):
      // `classList.add` on a class the row already carries is a no-op, so a second jump to
      // the SAME row inside the 1.5s window - two quick presses of "My line" - left the
      // class already present and the animation never restarted. Reading `offsetWidth`
      // forces the browser to flush the removal before the class goes back on, which is
      // what makes the animation actually replay from its first frame.
      row.classList.remove('jump-flash');
      void row.offsetWidth;
      row.classList.add('jump-flash');
      watch.flashTimer = window.setTimeout(
        () => row.classList.remove('jump-flash'),
        1500,
      );
    };

    const already = findRow();
    if (already) {
      land(already);
      return () => window.clearTimeout(watch.flashTimer);
    }

    // Not there yet - the grid's own render (and its own async gate) has not caught up with
    // this jump. Watch for it to land rather than guessing a delay.
    const observer = new MutationObserver(() => {
      const row = findRow();
      if (!row) return;
      land(row);
    });
    observer.observe(panel, { childList: true, subtree: true });
    watch.observer = observer;
    return () => {
      observer.disconnect();
      if (watch.observer === observer) watch.observer = null;
      window.clearTimeout(watch.flashTimer);
    };
    // Deliberately NOT `jumpTarget` itself - see the module doc above. `kind`/`nonce` are
    // the whole of what a jump IS; nothing else may re-run this effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jumpTarget?.kind, jumpTarget?.nonce]);

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
          title={dateCellText(row.original)}
        >
          {dateCellText(row.original)}
          {row.original.overdue_days && row.original.counted ? (
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
      // Per TYPE on a PER-BIN reading, because an S/O subtracts where an SPO adds and the
      // point of this footer is the one figure that already sits above the table: this
      // bin's own outstanding demand, the row's own "SO qty".
      //
      // D9 (captain, 3 Sep; AC-2.6c): on the GROUP reading it is the opposite mistake - the
      // ledger HAS a running balance (`balance`, below), and the S/O-only sum disagreed with
      // it on a site pool subtotal ("On hand 49 + 586 + 20, S/O 1, SPO 113 + 4" read Quantity
      // "1" beside a closing Available for Project of 385). The Total is the SIGNED NET of
      // every row listed instead - on hand and SPO add, S/O and Hold subtract, `row.delta`
      // already carries the sign - which is the same arithmetic the running column's own
      // last value is built from, so the two figures cannot disagree.
      footer: () => (
        <span className="tabular-nums">
          {fromMinor(
            isGroup
              ? rows.reduce((total, row) => total + row.delta, 0)
              : rows
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
      // R-K, S2: under the pools SET the running column is the pool's own share of each row's
      // balance, capped by the five-pool net the SAME stock-detail read now carries
      // (`five_pool_net`) - a GROUP set (`IB`, `BB`, ...) keeps the raw pile, unlabelled and
      // uncapped, exactly as it always has.
      const balanceHeading = isPoolsSection ? 'Available for Project' : 'Balance after';
      const fivePoolNet = isPoolsSection ? (detail.data?.five_pool_net ?? null) : null;
      const sharePct = detail.data?.pool_share_pct;
      const displayedBalance = (balance: string | null): string | null =>
        isPoolsSection
          ? (availableForProject(balance, fivePoolNet, sharePct) ?? balance)
          : balance;
      list.push({
        id: 'balance',
        // SORTED ON WHAT IS SHOWN (review round 2, nit 9). Under a site-pool section the
        // cell renders the SHARE of each balance, and sorting the raw pile put the rows in
        // an order the column's own numbers contradict - a floor and a cap are not
        // order-preserving, so two rows can read 12 and 12 off balances of 25 and 24.
        accessorFn: (row) => Number(displayedBalance(row.balance) || 0),
        header: ({ column }) => (
          <DataGridColumnHeader title={balanceHeading} column={column} />
        ),
        cell: ({ row }) => {
          const shown = displayedBalance(row.original.balance);
          return (
            <span
              data-testid={`stock-balance-${row.original.key}`}
              className={cn(
                'block truncate text-sm tabular-nums',
                emphasis(row.original),
                isNegative(shown) && 'text-destructive',
              )}
            >
              {shown}
            </span>
          );
        },
        // Where the group ends up once every row has been read. It is the subtotal's own
        // Available less two things the subtotal does not carry, both of them rows in this
        // list: THIS cell's own demand (the subtotal adds it back, because a line does not
        // compete with itself) and any hold taken from outside the group. Under the pools SET
        // this closing figure equals the Stock tab's own "Available for Project" summary cell
        // (AC-2.6b) - the same share formula, over the same closing balance.
        footer: () => {
          const closing =
            rows.length > 0 ? rows[rows.length - 1].balance : null;
          const shown = displayedBalance(closing);
          return (
            <span
              className={cn(
                'tabular-nums',
                isNegative(shown) && 'text-destructive',
              )}
            >
              {shown ?? '-'}
            </span>
          );
        },
        size: 130,
        minSize: 110,
        meta: { headerTitle: balanceHeading },
      });
    }

    return list;
  }, [
    isGroup,
    rows,
    isPoolsSection,
    detail.data?.five_pool_net,
    detail.data?.pool_share_pct,
  ]);

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
          // NO LOCAL "My line" TOOLBAR (retired, review round S3). This panel used to carry
          // its own, scrolling straight to the row with no flash - a second "My line" that
          // duplicated the sticky toolbar's own button (`BoardCellBreakdownDialog`), which
          // already reaches this exact row through `jumpTarget` and lands it WITH the flash.
          // Two buttons doing the same job, one of them worse, is not a second feature.
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
 *
 * A late-but-alive document sorts on its ASSUMED date (R-O, review fix round S5), never the
 * stated one it is dated after: the walk and the drill-down both plan against `as_of + grace`,
 * and a ledger ordered by the stated date would slot a document that is really landing in two
 * weeks in among documents from months ago, well ahead of demand it cannot actually cover.
 */
function compareByEngineDate(
  left: StockDetailRow,
  right: StockDetailRow,
): number {
  const leftDate = left.assumed_date ?? left.due_date ?? '';
  const rightDate = right.assumed_date ?? right.due_date ?? '';
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

/**
 * What the date cell says, in one place because three readings share it (R-O, 3 Sep 2026).
 *
 * A document the walk plans against a DIFFERENT day from the one it states says both:
 * "assumed 17 Sep 2026, stated 24 Jul 2026". The assumed day is what a promise gets made
 * on, and the stated one is what the buyer chases the supplier about, so printing only one
 * of them loses the half the reader needs. A document so late the walk counts it as nothing
 * says exactly that, because a date beside it would read as a promise.
 *
 * No new column: this is the existing cell's text.
 */
function dateCellText(row: StockDetailRow): string {
  if (!row.counted) return 'Not counted';
  const stated = row.due_date ? formatDateInMalaysia(row.due_date) : null;
  if (row.assumed_date) {
    const assumed = formatDateInMalaysia(row.assumed_date);
    return stated ? `assumed ${assumed}, stated ${stated}` : `assumed ${assumed}`;
  }
  if (stated) return stated;
  return row.doc_type === 'On hand' ? 'Held now' : 'Not stated';
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
  /**
   * The day the WALK plans a LATE document against (R-O, 3 September 2026). Set, the date
   * cell reads "assumed 17 Sep 2026, stated 24 Jul" - the assumed day is what a promise is
   * made on and the stated one is what the paperwork says, and a planner needs both.
   */
  assumed_date: string | null;
  /** False on a document so late the walk counts it as nothing: the row reads "not counted". */
  counted: boolean;
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
