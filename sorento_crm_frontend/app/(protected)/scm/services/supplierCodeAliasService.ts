/**
 * ============================================================================
 * What a supplier's code means (R16, F11)
 * ============================================================================
 * Layering: MatchToProductDialog / the loading plan / the PI detail
 *   -> THIS service -> lib/api-client -> backend.
 *
 * ── BACKEND CONTRACT (app/api/v1/scm/fulfilment.py) ────────────────────────
 *  GET    /api/v1/scm/supplier-code-aliases?supplier_id      -> 200 { data: SupplierCodeAlias[] }
 *  GET    /api/v1/scm/supplier-code-aliases/unmatched?supplier_id
 *                                                            -> 200 { data: UnmatchedSupplierCode[] }
 *  POST   /api/v1/scm/supplier-code-aliases                  -> 201 SupplierCodeAliasWritten
 *         Body: { supplier_id, supplier_code, product_id }. Replaces any earlier ruling and
 *         RE-BINDS the rows already uploaded under that code - the counts come back, so the
 *         screen can say what the decision just moved.
 *  POST   /api/v1/scm/supplier-code-aliases/dismiss          -> 201 SupplierCodeDismissed
 *         Body: { supplier_id, supplier_code }. "None of ours": records a ruling with no
 *         product, UNBINDS the rows already uploaded under that code, and takes it out of
 *         the unmatched queue.
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
  | 'manual'
  | 'dismissed'
  | 'alias';

export interface SupplierCodeAlias {
  id: string;
  supplier_code: string;
  /** Null on a dismissal: "none of ours" is a ruling that names no product. */
  product_code: string | null;
  product_name: string | null;
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
  product_id: string;
  product_code: string;
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

export async function listUnmatchedSupplierCodes(
  supplierId: string,
): Promise<UnmatchedSupplierCode[]> {
  const res = await apiFetch(
    `/api/v1/scm/supplier-code-aliases/unmatched?supplier_id=${encodeURIComponent(supplierId)}`,
  );
  const body = await readJson<{ data: UnmatchedSupplierCode[] }>(
    res,
    'Failed to load the codes that match nothing',
  );
  return body.data ?? [];
}

export async function matchSupplierCode(body: {
  supplier_id: string;
  supplier_code: string;
  product_id: string;
}): Promise<SupplierCodeAliasWritten> {
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

export async function forgetSupplierCodeMatch(id: string): Promise<void> {
  const res = await apiFetch(`/api/v1/scm/supplier-code-aliases/${id}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to forget the match'));
}
