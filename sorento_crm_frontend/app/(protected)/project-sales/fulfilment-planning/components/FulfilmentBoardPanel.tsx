'use client';

import * as React from 'react';
import { ArrowLeft, PackageSearch } from 'lucide-react';
import {
  Alert,
  AlertContent,
  AlertDescription,
  AlertIcon,
  AlertTitle,
} from '@/components/ui/alert';
import { AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import {
  useReconciliationMutations,
  usePlanningBoard,
} from '../../_shared/hooks/useFulfilmentPlanning';
import { ConfirmSupplyError } from '../../_shared/services/fulfilmentPlanningService';
import {
  commitPreviewFor,
  confirmLinesFor,
  standingsFor,
} from '../../_shared/lib/fulfilmentBoard';
import type {
  BoardCell,
  BoardCommitPreview,
  BoardDecision,
  BoardDraft,
  BoardGranularity,
  BoardOrderStanding,
  BoardPolicy,
  SupplyFailingLine,
} from '../../_shared/types/fulfilmentPlanning.types';
import { BoardCellBreakdownDialog } from './BoardCellBreakdownDialog';
import { FulfilmentBoardMatrix } from './FulfilmentBoardMatrix';

/** The calendar control the captain asked for: day, week or month (PLAN 13.3). */
const GRANULARITY_OPTIONS = [
  { value: 'day', label: 'By day' },
  { value: 'week', label: 'By week' },
  { value: 'month', label: 'By month' },
];

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
  const [granularity, setGranularity] = React.useState<BoardGranularity>('week');
  const [draft, setDraft] = React.useState<BoardDraft>({});
  const [openCell, setOpenCell] = React.useState<BoardCell | null>(null);
  const [previewPolicy, setPreviewPolicy] = React.useState(false);
  /** Which 30-day window the day view is showing. Undefined lets the server choose the first. */
  const [dayWindow, setDayWindow] = React.useState<string | undefined>(undefined);

  const board = usePlanningBoard(
    soNumbers,
    granularity,
    previewPolicy,
    dayWindow ? { dayWindow } : {},
  );

  /**
   * Move the day window by a whole window at a time.
   *
   * The FIRST window is the server's: it opens on the earliest date still to come, falling
   * back to the earliest owed when everything is past, and nothing here re-anchors it. This
   * control only moves off whatever is currently rendered, so it cannot drift out of step with
   * the columns it is scrolling.
   *
   * Day is the only granularity with a window. Week and month need none: only periods actually
   * owed become columns, so the 50-order cap tops out around 57 week or 24 month columns, and
   * a control to page through them would be a knob for a problem nobody has.
   */
  const shiftWindow = React.useCallback(
    (direction: 1 | -1) => {
      const dated = (board.data?.dateBuckets ?? []).filter(
        (bucket) => bucket.kind === 'dated' && bucket.start,
      );
      const anchor = dated[0]?.start;
      if (!anchor) return;
      const next = new Date(`${anchor}T00:00:00Z`);
      next.setUTCDate(next.getUTCDate() + direction * dated.length);
      setDayWindow(next.toISOString().slice(0, 10));
    },
    [board.data],
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
  /** Which order is in flight, and what the server refused, per order. */
  const [confirming, setConfirming] = React.useState<string | null>(null);
  const [refusals, setRefusals] = React.useState<Record<string, SupplyFailingLine[]>>({});

  /**
   * Commit one order's decided lines through the existing per-order confirmation.
   *
   * The board writes nothing of its own (13.4): this is the SAME endpoint the sheet posts to,
   * so there is one write path and one set of invariants. Partial by construction - a line the
   * body does not name is left undecided and keeps flowing to reorder planning.
   *
   * On success the confirmed keys leave the draft, because they are in the database now and a
   * draft that still claimed them would offer to confirm them twice. On a REFUSAL the draft is
   * untouched: the planner composed that, the server rejected it, and making them do it again
   * is the one outcome that would teach them not to use the board.
   */
  const confirmOrder = React.useCallback(
    async (standing: BoardOrderStanding) => {
      const psoId = standing.project_sales_order_id;
      if (!psoId || !board.data) return;
      const contributions = board.data.cells.flatMap((cell) => cell.contributions);
      const lines = confirmLinesFor(contributions, standing.sales_order_id, draft);
      if (lines.length === 0) return;

      setConfirming(standing.sales_order_id);
      setRefusals((current) => ({ ...current, [standing.sales_order_id]: [] }));
      try {
        await confirm.mutateAsync({ psoId, body: { lines } });
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
    [board.data, confirm, draft],
  );

  /**
   * Which order each contribution key belongs to, ACCUMULATED across every board shown.
   *
   * A verdict is only ever given on a cell that was on screen, so every draft key passes
   * through here once. Rebuilding this from the current board instead would drop a verdict the
   * moment its cell left the day window, and the counter would fall as the planner scrolled.
   * The key is stored, never parsed: the server owns its format (deviation 5).
   */
  const owners = React.useRef<Map<string, string>>(new Map());
  for (const cell of board.data?.cells ?? []) {
    for (const contribution of cell.contributions) {
      owners.current.set(contribution.key, contribution.sales_order_id);
    }
  }

  /**
   * The standings are the SERVER's, off `board.orders`, which counts every row of the
   * selection. Only the verdicts are ours.
   *
   * Counting them from `cells` was a live defect: at day granularity the cells are a 30-day
   * window, so a forty-line order read "3 of 3 lines decided" and the Confirm beside it
   * promised to leave nothing behind.
   */
  const standings = React.useMemo<BoardOrderStanding[]>(() => {
    if (!board.data) return [];
    return standingsFor(board.data.orders, owners.current, draft);
  }, [board.data, draft]);

  const previews = React.useMemo<Record<string, BoardCommitPreview>>(() => {
    if (!board.data) return {};
    return Object.fromEntries(
      standings.map((standing) => [
        standing.sales_order_id,
        commitPreviewFor(standing),
      ]),
    );
  }, [standings, board.data]);

  const bucketLabel = React.useMemo(() => {
    const map = new Map<string, string>();
    for (const bucket of board.data?.dateBuckets ?? []) map.set(bucket.key, bucket.label);
    return map;
  }, [board.data]);

  // The cell the dialog is showing has to be re-read from the board on every render, or the
  // decision pills inside it would keep the shape they had when it was opened.
  const liveCell = React.useMemo(() => {
    if (!openCell || !board.data) return null;
    return (
      board.data.cells.find(
        (cell) =>
          cell.item_code === openCell.item_code && cell.bucket_key === openCell.bucket_key,
      ) ?? null
    );
  }, [openCell, board.data]);

  /**
   * How many LINES of the selection are already past their required date.
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
          {/* Last in the row and `ghost`: going back is secondary to the control that decides
              what the board shows, and an outline button beside the select out-shouted it. */}
          <Button type="button" variant="ghost" size="sm" onClick={onBack}>
            <ArrowLeft className="size-4" aria-hidden />
            Back to the worklist
          </Button>
        </div>
      </div>

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
                  {`${pastTotal.lines} of ${pastTotal.allLines} lines are already past their required date`}
                </AlertTitle>
              </AlertContent>
            </Alert>
          )}

          {/* Which ranking produced what is on screen. Always stated: under the live policy
              every row scores 0.0, and a planner who cannot see that is looking at a flat
              ranking believing it is a considered one (PLAN 13.5). */}
          <PolicyNote
            policy={board.data.policy}
            previewing={previewPolicy}
            onPreviewChange={setPreviewPolicy}
          />

          <FulfilmentBoardMatrix
            dateBuckets={board.data.dateBuckets}
            productRows={board.data.productRows}
            cells={board.data.cells}
            decidedKeys={decidedKeys}
            onOpenCell={(cell) => setOpenCell(cell)}
          />

          <Card>
            <CardHeader className="block">
              <h3 className="text-sm font-semibold">Commit</h3>
              <p className="mt-0.5 text-sm text-muted-foreground">
                One confirmation per sales order, each atomic across the lines it commits.
                Anything left undecided stays outstanding and keeps flowing to reorder planning.
              </p>
              {/* Two consequences a planner would otherwise wait for and never see. Stated
                  rather than papered over, and NOT linked: the Order Inquiry list is
                  project-scoped, so a link from here would open a list this order is not on,
                  which is worse than no link. */}
              <p className="mt-0.5 text-sm text-muted-foreground">
                Confirmed Buy rows reach purchasing on the sales order itself. An adopted order
                raises no purchasing task and sends no notification.
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
  onConfirm,
}: {
  standing: BoardOrderStanding;
  preview?: BoardCommitPreview;
  busy: boolean;
  /** The lines the server would not take, kept beside the order that owns them. */
  refused: SupplyFailingLine[];
  onConfirm: () => void;
}) {
  const committing = preview?.committing ?? 0;
  const leaving = preview?.leaving_undecided ?? 0;
  const blocked = preview?.blocked ?? 0;
  // An order nobody has adopted has no planning record, and the confirm endpoint is keyed on
  // one. Saying so beats a button that posts to a path that does not exist.
  const plannable = Boolean(standing.project_sales_order_id);
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
            {!plannable
              ? 'Nobody has started planning this sales order yet.'
              : committing === 0
                ? 'Nothing decided yet on this order.'
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
            disabled={committing === 0 || !plannable || busy}
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

/**
 * The policy the board ranked by, named on screen.
 *
 * The live seeded row weights only `po_document_sequence`, which a sales-order line cannot have,
 * so it scores every contributor 0.0 and ranks nothing. That is not a bug to hide behind a
 * plausible-looking order; it is the thing the captain has to decide about (PLAN 13.5).
 */
function PolicyNote({
  policy,
  previewing,
  onPreviewChange,
}: {
  policy: BoardPolicy;
  previewing: boolean;
  onPreviewChange: (next: boolean) => void;
}) {
  // The weights are shown as evidence; whether they SEPARATE anything is the server's verdict
  // (deviation 1), because a weighted-but-constant factor looks healthy from here.
  const weights = Object.entries(policy.factors).filter(([, weight]) => Number(weight) > 0);
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-border px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0 text-sm">
        <span className="text-muted-foreground">Ranked by </span>
        <span className="font-medium">{policy.name}</span>
        {policy.is_preview && (
          <span className="ms-2 rounded bg-amber-100 px-1 text-[10px] font-medium text-amber-800">
            Preview, not live
          </span>
        )}
      </div>
      <div className="flex min-w-0 flex-wrap items-center gap-3">
        {policy.discriminates_nothing ? (
          <p className="min-w-0 text-sm text-destructive break-words">
            This policy weights nothing that separates these rows, so every one scores the same
            and the ranking is flat.
          </p>
        ) : (
          <p className="min-w-0 text-sm text-muted-foreground break-words">
            {weights.map(([key, weight]) => `${key} ${weight}`).join(' · ')}
          </p>
        )}
        {/* A what-if, never an activation: previewing shows what a fair weighting would do to
            these real orders without changing what container loading and stock assignment use. */}
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="shrink-0"
          onClick={() => onPreviewChange(!previewing)}
        >
          {previewing ? 'Back to the live policy' : 'Preview a fairer weighting'}
        </Button>
      </div>
    </div>
  );
}
