/**
 * ============================================================================
 * Stock Debt - feature service (S2, AC-S2-6 / AC-S2-7)
 * ============================================================================
 * Layering: UI -> hooks (`useStockDebtQuery`) -> THIS service -> lib/api-client
 * -> backend.
 *
 * Phase 2: the fixture is gone and both functions call the backend. The contract
 * below is what was built against it and what the routes answer, so it stays here
 * as the one place the two sides are stated together.
 *
 * ── PHASE-2 BACKEND CONTRACT ────────────────────────────────────────────────
 * Both routes live under the `projects` domain router and both require
 * `projects.stock_debt.view` (AC-S2-8, R22; permission + grant sweep shipped in
 * migration 443 with S1).
 *
 * 1) The month x product board (AC-S2-6)
 *
 *      GET /api/v1/project-sales/stock-debt
 *          ?page=<1-based>      standard `buildDataGridParams` paging
 *          &limit=<n>
 *          &query=<text>        product code or name
 *          &group=<BB|IB|...>   ownership group; limits the stock AND the demand
 *                               read to that group, so the balances are recomputed
 *                               rather than filtered
 *          &only_debt=<bool>    drop rows with no negative month (default true on
 *                               the screen)
 *
 *      -> 200 {
 *           data: [{
 *             product_id, product_code, product_name,
 *             months: [{ key: 'YYYY-MM', balance, tone: 'red'|'amber'|'green' }],
 *             tba, undated, unlocated
 *           }],
 *           pagination: { total, page, limit },
 *           months:    ['YYYY-MM', ...],   the column axis
 *           tba_month: 'YYYY-MM',          the policy's `tba_date_from`, by month
 *           groups:    ['BB', ...]         what the flag admits, for the select
 *         }
 *
 *      `data[].months` carries one entry per axis key, in axis order.
 *      Rows are sorted by EARLIEST RED MONTH, then product code; a row with no red
 *      month sorts after every row that has one.
 *      `tba`, `undated` and `unlocated` are plain signed totals - the demand dated on
 *      or after `tba_date_from`, the demand with no date, and the demand booked at no
 *      warehouse at all. None of the three draws supply (R14), so they carry no tone and
 *      the screen renders them as informational.
 *
 *      The three axis fields are envelope-level and NOT per row, because the axis is
 *      a property of the whole filtered set: derived per page, the columns would
 *      change under the reader as they page.
 *
 * 2) The cell drill (AC-S2-7, R28)
 *
 *      GET /api/v1/project-sales/stock-debt/{product_id}/cell
 *          ?month=<YYYY-MM | tba | undated | unlocated>
 *          &group=<BB|IB|...>   the group the BOARD is narrowed to. Same meaning as on
 *                               the list: it narrows the span the balance is recomputed
 *                               from, so the drill foots with the cell that opened it.
 *                               Omitted = the whole book.
 *
 *      -> 200 {
 *           demand: [{ so_number, agent_code, warehouse_code, required_date, open_qty,
 *                      assigned_qty, assigned_source,
 *                      status: 'covered'|'late'|'short'|'pinned' }],
 *           supply: [{ kind: 'on_hand'|'spo'|'po', ref, warehouse_code, date,
 *                      bought_for, qty, overdue, assigned_to: [{ so_number, qty }] }]
 *         }
 *
 *      `demand` = the lines whose required date falls in that month, or every TBA /
 *      undated line for those two keys. `supply` = the events dated in that month:
 *      on hand by bin for the current month, an SPO at its arrival, a PO line at
 *      `issue + lead` (R29) carrying its `expected_date` as `bought_for` (display
 *      only, R30). An event whose arrival has passed with nothing received is listed
 *      with `overdue: true` and counted as nothing (R31).
 *
 * The shapes are typed field for field in `types/stockDebt.types.ts`; they are not
 * restated here, so the two cannot drift.
 *
 * ── PERMISSION ──────────────────────────────────────────────────────────────
 * `projects.stock_debt.view` PRESUMES `projects.projects.view`. The page sits under
 * `app/(protected)/project-sales/layout.tsx`, which gates every child of the section
 * on `projects.projects.view`, and `RequireAccess` takes ONE permission - it has no
 * any-of mode, and building one for a single caller is machinery nobody has asked for
 * yet. Migration 443's sweep grants `stock_debt.view` to exactly the roles that hold
 * `projects.view`, so the presumption holds for every role that can reach the entry;
 * recorded in the UAC as AC-S2-8. The trigger for an any-of gate is the first role that
 * needs Stock Debt WITHOUT the section it lives in.
 *
 * ── ERROR SHAPE ─────────────────────────────────────────────────────────────
 * The standard `AppException` envelope the global handler in `app/main.py`
 * serialises, read with `extractApiError(res, fallback)` and surfaced as an `Error`
 * message - which is what the page's error state renders beside its Retry.
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { StockDebtCell, StockDebtListResponse } from '../types/stockDebt.types';

/** What the board asks for: a page, a needle, a group and the debt-only switch. */
export interface StockDebtListParams {
  pageIndex: number;
  pageSize: number;
  query: string;
  /** Ownership group, or '' for every group. */
  group: string;
  onlyDebt: boolean;
}

/** The month x product board (AC-S2-6). */
export async function getStockDebtList(
  params: StockDebtListParams,
): Promise<StockDebtListResponse> {
  const search = buildDataGridParams(
    {
      pageIndex: params.pageIndex,
      pageSize: params.pageSize,
      searchQuery: params.query,
    },
    { group: params.group, only_debt: params.onlyDebt },
  );
  const res = await apiFetch(`/api/v1/project-sales/stock-debt?${search}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load stock debt'));
  return (await res.json()) as StockDebtListResponse;
}

/**
 * The demand and supply behind one cell (AC-S2-7). `month` is `YYYY-MM`, `tba`,
 * `undated` or `unlocated`; `group` is the board's own narrowing, passed through so the
 * drill is recomputed over the same span the cell was.
 */
export async function getStockDebtCell(
  productId: string,
  month: string,
  group?: string,
): Promise<StockDebtCell> {
  const search = new URLSearchParams({ month });
  if (group) search.set('group', group);
  const res = await apiFetch(
    `/api/v1/project-sales/stock-debt/${encodeURIComponent(productId)}/cell?${search}`,
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load the cell'));
  return (await res.json()) as StockDebtCell;
}
