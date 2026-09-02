/**
 * ============================================================================
 * API CONTRACT - spec verification (PR 3)
 * ============================================================================
 *
 * Written out here because the frontend was built against it before any of it
 * existed (Phase 1). The calls below are that contract, now against the real API;
 * a deviation updates this block and both sides together.
 *
 * Base path: /api/v1/master-data/product-specifications
 * All routes sit on the existing router, so they inherit its module guard.
 *
 * READS
 *
 *   GET /verification/worklist                        perm master_data.products.view
 *     query: page, limit, query (code/name search), state, class_label,
 *            include_discontinued=false, sort=default|coverage|code, dir=asc|desc
 *     200: { data: Row[],
 *            pagination: { total, page, limit },
 *            summary: { total, verified, needs_reverify, unverified },
 *            classes: string[] }
 *
 *     Row: { product_id, product_code, product_name, class_label|null,
 *            brand_name|null, is_discontinued,
 *            coverage: { have, applicable, items: [{ spec_key, label, value }] },
 *            open_exceptions, values_hash, verification: VerificationBlock }
 *
 *     `coverage.items` is the denominator itemised: every APPLICABLE registry key for
 *     that row, by the same gate rule the `applicable` count uses, with the registry
 *     label and the stored ENTRY (`{ value, unit? }`) or null when the key is unfilled,
 *     sorted by label. It is what the Coverage cell opens, so a reviewer can judge a
 *     code without leaving the list (captain ruling 2026-08-17). `open_exceptions` is
 *     rendered as a warning pill on the Coverage cell, "{n} need a human" (AC-F.4,
 *     design-language D11) - the count only, no reasons on this payload.
 *
 *     VerificationBlock: { state: 'unverified'|'verified'|'needs_reverify',
 *            verified_by_name|null, verified_at|null,
 *            invalidated_at|null, invalidated_reason|null, invalidated_by_name|null,
 *            invalidated_diff: null | { changed: [{ spec_key, was, now }] } }
 *
 *     `was` / `now` are the stored spec ENTRIES - `{ value, unit? }` as `spec.values`
 *     holds them - or null when the key was absent on that side. They are not scalars:
 *     render them through `readableEntry`, never a scalar formatter.
 *
 *     `product_id` is the copy of the code in the caller's company scope, so the
 *     row click resolves even though the worklist is keyed on `product_code`.
 *     Default order (C6): needs_reverify first, then unverified grouped by
 *     class_label then product_code, verified last. Coverage is computed inline
 *     in the worklist SQL against the registry (AC-D.7), never by calling
 *     keys-for-product per code. Discontinued codes are excluded by default
 *     (AC-D.6). `summary` counts the same set as the list MINUS the `state`
 *     filter, so "Verified N of M" stays honest while a state filter is applied.
 *     `classes` are the class filter's OWN options: the distinct class labels over
 *     the same scope, computed before the class and state filters so filtering to a
 *     class never empties the dropdown that did the filtering. No options endpoint is
 *     minted and the spec registry is NOT the source - its `class` key is open
 *     vocabulary and its allowed_values are deliberately empty, so the labels only
 *     exist on the rows themselves.
 *
 *   GET /by-product/{productId}   (existing route, PR 2)
 *     gains `verification: VerificationBlock` and `values_hash` (AC-D.14), so the
 *     Specifications tab needs no second round trip.
 *
 * WRITES  (all perm master_data.products.edit, AC-D.15)
 *
 *   POST /verification/verify           body { product_code, values_hash }
 *     200: { product_code, outcome: 'verified'|'already_verified',
 *            verification, values_hash }
 *     409: { error: 'values_changed', values_hash: <current>, verification }
 *     The client echoes the hash it was shown; the handler locks the code's spec
 *     rows and compares in the same transaction (AC-D.4). A moved hash is the ONLY
 *     refusal: the open-exception gate was dropped with the exceptions UI (captain
 *     ruling 2026-08-17), so a code with open exceptions verifies normally.
 *
 *   POST /verification/verify-bulk      body { items: [{ product_code, values_hash }] }
 *     200: { results: [{ product_code,
 *                        outcome: 'verified'|'already_verified'|'values_changed'
 *                                |'not_found',
 *                        values_hash?, verification? }],
 *            counts: { verified, skipped } }
 *     Per-code, never all-or-nothing (AC-D.11). It is a loop over the SAME
 *     service function as the single verify, so bulk cannot become the laxer
 *     path (AC-D.16). `values_hash` comes back on a refused code so the row can
 *     refresh without a reload.
 *
 *   POST /verification/unverify         body { product_code }
 *     200: { product_code, outcome: 'unverified'|'no_change', verification }
 *   POST /verification/unverify-bulk    body { product_codes: [...] }
 *     200: { results: [{ product_code, outcome, verification? }],
 *            counts: { unverified, no_change } }
 *     Unverify has no hash compare (a claim is being
 *     removed, not made), lands on `unverified` rather than needs_reverify, keeps
 *     the original verified_by / verified_at on the row, and is idempotent on a
 *     code with no history (AC-D.20, AC-D.21). No reason field: AC-D.1's column
 *     list has nowhere to store one (recorded as a deliberate omission).
 *
 * THE ROW BUTTONS CALL THE BULK ROUTES
 *
 * A per-row Verify is a bulk of one (AC-D.23), so there is exactly one code path
 * to keep honest. The single routes above are the Specifications tab's, where a
 * refusal has to be rendered rather than counted.
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type {
  SpecVerificationWorklistParams,
  SpecVerificationWorklistResponse,
  UnverifyBulkResponse,
  UnverifyResponse,
  VerificationBlock,
  VerifyBulkResponse,
  VerifyItem,
  VerifyResponse,
} from '../types/specVerification.types';

const BASE = '/api/v1/master-data/product-specifications/verification';

export async function getSpecVerificationWorklist(
  params: SpecVerificationWorklistParams,
): Promise<SpecVerificationWorklistResponse> {
  const search = buildDataGridParams(params, {
    state: params.state || undefined,
    class_label: params.class_label || undefined,
    include_discontinued: params.include_discontinued ? 'true' : undefined,
  });
  const response = await apiFetch(`${BASE}/worklist?${search.toString()}`);
  if (!response.ok) {
    throw new Error(
      await extractApiError(
        response,
        'Failed to load the verification worklist',
      ),
    );
  }
  return response.json();
}

export async function verifySpecBulk(
  items: VerifyItem[],
): Promise<VerifyBulkResponse> {
  const response = await apiFetch(`${BASE}/verify-bulk`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to verify'));
  }
  return response.json();
}

export async function unverifySpecBulk(
  productCodes: string[],
): Promise<UnverifyBulkResponse> {
  const response = await apiFetch(`${BASE}/unverify-bulk`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ product_codes: productCodes }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to unverify'));
  }
  return response.json();
}

/**
 * The single verify was refused because the values moved under the reviewer.
 *
 * Its own error type for the reason `SpecSimilarError` has one: the 409 is a product
 * answer rather than a failure - the screen is stale and has to be re-read, and the
 * current hash comes back so it can be. `extractApiError` is string-only and cannot
 * carry that, so this call reads the body itself.
 */
export class SpecVerifyConflictError extends Error {
  readonly reason: 'values_changed';
  /** The hash the server holds now. */
  readonly valuesHash?: string;
  readonly verification?: VerificationBlock;

  constructor(
    reason: 'values_changed',
    message: string,
    extra: {
      valuesHash?: string;
      verification?: VerificationBlock;
    } = {},
  ) {
    super(message);
    this.name = 'SpecVerifyConflictError';
    this.reason = reason;
    this.valuesHash = extra.valuesHash;
    this.verification = extra.verification;
  }
}

interface ConflictBody {
  error?: string;
  message?: string;
  values_hash?: string;
  verification?: VerificationBlock;
  /** The AppException envelope, read as a fallback so either serialisation lands. */
  detail?: ConflictBody | string | null;
}

async function throwVerifyError(
  response: Response,
  fallback: string,
): Promise<never> {
  if (response.status === 409) {
    let body: ConflictBody | null = null;
    try {
      body = await response.clone().json();
    } catch {
      body = null;
    }
    const carrier =
      body?.error !== undefined
        ? body
        : body?.detail && typeof body.detail === 'object'
          ? body.detail
          : null;
    if (carrier?.error === 'values_changed') {
      // The server's own sentence beats the generic one this call site would show.
      throw new SpecVerifyConflictError(
        carrier.error,
        carrier.message || fallback,
        {
          valuesHash: carrier.values_hash,
          verification: carrier.verification,
        },
      );
    }
  }
  throw new Error(await extractApiError(response, fallback));
}

/**
 * Verify ONE code, from its own Specifications tab.
 *
 * The bulk route is what the worklist calls, down to a bulk of one (AC-D.23); this is
 * the single route, because the tab has to render the refusal rather than count it.
 */
export async function verifySpec(body: VerifyItem): Promise<VerifyResponse> {
  const response = await apiFetch(`${BASE}/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    await throwVerifyError(response, 'Could not verify this product');
  }
  return response.json();
}

export async function unverifySpec(body: {
  product_code: string;
}): Promise<UnverifyResponse> {
  const response = await apiFetch(`${BASE}/unverify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(
      await extractApiError(response, 'Could not unverify this product'),
    );
  }
  return response.json();
}
