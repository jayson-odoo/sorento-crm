/**
 * ============================================================================
 * What a supplier's code means (R16, F11)
 * ============================================================================
 * Layering: MatchToProductDialog / the loading plan / the PI detail
 *   -> THIS service -> lib/api-client -> backend.
 *
 * ── BACKEND CONTRACT (app/api/v1/scm/fulfilment.py) ────────────────────────
 *  GET    /api/v1/scm/supplier-code-aliases?supplier_id      -> 200 { data: SupplierCodeAlias[] }
 *  GET    /api/v1/scm/supplier-code-aliases/unmatched?plan_id
 *                                                            -> 200 { data: UnmatchedSupplierCode[] }
 *         Scoped to ONE loading plan (S6, AC-C7): the unknown codes on the stock rows and
 *         invoice lines stamped with that plan, never the supplier's other snapshots. A
 *         "No file" plan answers with an empty list.
 *  POST   /api/v1/scm/supplier-code-aliases                  -> 201 SupplierCodeAliasWritten
 *         Body: { supplier_id, supplier_code, product_id | product_set_id } - exactly one of
 *         the two (R19). Replaces any earlier ruling and RE-BINDS the rows already uploaded
 *         under that code - the counts come back, so the screen can say what the decision
 *         just moved.
 *  POST   /api/v1/scm/supplier-code-aliases/dismiss          -> 201 SupplierCodeDismissed
 *         Body: { supplier_id, supplier_code }. "None of ours": records a ruling with no
 *         product, UNBINDS the rows already uploaded under that code, and takes it out of
 *         the unmatched queue.
 *  POST   /api/v1/scm/supplier-code-aliases/rematch          -> 200 SupplierCodeRematched
 *         Body: { plan_id }. Runs the ladder again over THIS plan's rows still unbound, so a
 *         product added after the upload binds without the file being uploaded again.
 *  DELETE /api/v1/scm/supplier-code-aliases/{id}             -> 200 { deleted, rebound_* }
 *         Forgets the ruling - a match or a dismissal - and puts those rows back to
 *         whatever the ladder says now.
 *  Auth: read `scm.dashboard.view`; both writes `scm.reorder.run`.
 *
 * A supplier writes their own spelling of our code - reordered tokens, a trap size ours
 * omits. The ladder answers what it can and remembers it; this is where a person answers
 * the rest, and corrects the ladder where it guessed wrong.
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

/** Which rung bound a code - `exact` never appears here, only worked-out answers. */
export type SupplierCodeRung =
  | 'separator'
  | 'token_set'
  | 'size_drop'
  // The set rungs (R20). No `set_size_drop`: a set carries no description to confirm a size
  // against, so a code like `CWC605-RL-180` is answered by a person, never derived.
  | 'set_exact'
  | 'set_separator'
  | 'set_token_set'
  | 'manual'
  | 'dismissed'
  | 'alias';

export interface SupplierCodeAlias {
  id: string;
  supplier_code: string;
  /** Null on a dismissal, and null on a ruling that names a SET rather than a product. */
  product_code: string | null;
  product_name: string | null;
  /** The SET this code names, when it names one (R19). Null otherwise. */
  set_code: string | null;
  set_name: string | null;
  /**
   * `auto` for a bind the ladder worked out, `manual` for a person's own pick,
   * `dismissed` for a code ruled to be nothing we hold.
   */
  source: 'auto' | 'manual' | 'dismissed';
  matched_by: SupplierCodeRung | null;
  created_by: string | null;
  created_at: string | null;
}

/** One code the supplier sent that binds to nothing we hold. */
export interface UnmatchedSupplierCode {
  item_code: string;
  /** The supplier's own words for the item - what the person matching it recognises. */
  product_name: string | null;
  brand: string | null;
  spec: string | null;
  qty_packed: number;
  qty_unfinished: number;
  as_of: string | null;
}

export interface SupplierCodeAliasWritten {
  id: string;
  supplier_code: string;
  /** Null when the ruling names a SET - the two are mutually exclusive. */
  product_id: string | null;
  product_code: string | null;
  product_set_id: string | null;
  set_code: string | null;
  set_name: string | null;
  source: 'auto' | 'manual';
  matched_by: SupplierCodeRung | null;
  /** What the decision just moved - stock-list rows and invoice lines already on file. */
  rebound_stock_rows: number;
  rebound_invoice_lines: number;
}

async function readJson<T>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) throw new Error(await extractApiError(res, fallback));
  return (await res.json()) as T;
}

export async function listSupplierCodeAliases(
  supplierId: string,
): Promise<SupplierCodeAlias[]> {
  const res = await apiFetch(
    `/api/v1/scm/supplier-code-aliases?supplier_id=${encodeURIComponent(supplierId)}`,
  );
  const body = await readJson<{ data: SupplierCodeAlias[] }>(
    res,
    'Failed to load the matched codes',
  );
  return body.data ?? [];
}

/**
 * The unknown codes on ONE plan's statement.
 *
 * ── CONTRACT CHANGED BY S6 ─────────────────────────────────────────────────
 * `plan_id` replaces `supplier_id`. The queue used to be supplier-wide, which is how a
 * "No file" plan for ROYAL MIRROR showed 79 unknown codes off a stock list somebody had
 * uploaded from a different plan. It now reads only the `supplier_inventory` rows and
 * `proforma_invoice_line` rows stamped with this plan, so a plan with no file has nothing
 * to answer. The memory (`listSupplierCodeAliases`) stays per SUPPLIER: a ruling is the
 * supplier's, not the plan's.
 */
export async function listUnmatchedSupplierCodes(
  planId: string,
): Promise<UnmatchedSupplierCode[]> {
  const res = await apiFetch(
    `/api/v1/scm/supplier-code-aliases/unmatched?plan_id=${encodeURIComponent(planId)}`,
  );
  const body = await readJson<{ data: UnmatchedSupplierCode[] }>(
    res,
    'Failed to load the codes that match nothing',
  );
  return body.data ?? [];
}

/** Exactly one of the two, which is what the backend refuses to be given both or neither. */
export type SupplierCodeTarget = { product_id: string } | { product_set_id: string };

export async function matchSupplierCode(
  body: {
    supplier_id: string;
    supplier_code: string;
  } & SupplierCodeTarget,
): Promise<SupplierCodeAliasWritten> {
  const res = await apiFetch('/api/v1/scm/supplier-code-aliases', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return readJson<SupplierCodeAliasWritten>(res, 'Failed to record the match');
}

/** What comes back from a dismissal: the ruling, and what it just UNBOUND. */
export interface SupplierCodeDismissed {
  id: string;
  supplier_code: string;
  product_id: null;
  product_code: null;
  product_set_id: null;
  set_code: null;
  set_name: null;
  source: 'dismissed';
  matched_by: 'dismissed';
  rebound_stock_rows: number;
  rebound_invoice_lines: number;
}

export async function dismissSupplierCode(body: {
  supplier_id: string;
  supplier_code: string;
}): Promise<SupplierCodeDismissed> {
  const res = await apiFetch('/api/v1/scm/supplier-code-aliases/dismiss', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return readJson<SupplierCodeDismissed>(res, 'Failed to dismiss the code');
}

/** What the ladder answered on a second pass, and what is left to answer by hand. */
export interface SupplierCodeRematched {
  inventory_bound: number;
  invoice_lines_bound: number;
  still_unmatched: number;
}

/** Re-run the ladder over THIS plan's still-unbound rows (S6: `plan_id`, not
 *  `supplier_id`) - the same scope the queue above reads. */
export async function rematchSupplierCodes(body: {
  plan_id: string;
}): Promise<SupplierCodeRematched> {
  const res = await apiFetch('/api/v1/scm/supplier-code-aliases/rematch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return readJson<SupplierCodeRematched>(res, 'Failed to refresh the matching');
}

export async function forgetSupplierCodeMatch(id: string): Promise<void> {
  const res = await apiFetch(`/api/v1/scm/supplier-code-aliases/${id}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to forget the match'));
}
