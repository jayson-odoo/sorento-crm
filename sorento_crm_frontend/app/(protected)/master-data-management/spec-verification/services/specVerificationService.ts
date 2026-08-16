/**
 * ============================================================================
 * API CONTRACT - spec verification (PR 3)
 * ============================================================================
 *
 * Written out here because the frontend was built against it before any of it
 * existed (Phase 1). Phase 2 implements exactly this and swaps the mock bodies
 * below for `apiFetch`; a deviation updates this block and both sides together.
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
 *            summary: { total, verified, needs_reverify, unverified } }
 *
 *     Row: { product_id, product_code, product_name, class_label|null,
 *            brand_name|null, is_discontinued,
 *            coverage: { have, applicable }, open_exceptions,
 *            values_hash, verification: VerificationBlock }
 *
 *     VerificationBlock: { state: 'unverified'|'verified'|'needs_reverify',
 *            verified_by_name|null, verified_at|null,
 *            invalidated_at|null, invalidated_reason|null, invalidated_by_name|null,
 *            invalidated_diff: null | { changed: [{ spec_key, was, now }] } }
 *
 *     `product_id` is the copy of the code in the caller's company scope, so the
 *     row click resolves even though the worklist is keyed on `product_code`.
 *     Default order (C6): needs_reverify first, then unverified grouped by
 *     class_label then product_code, verified last. Coverage is computed inline
 *     in the worklist SQL against the registry (AC-D.7), never by calling
 *     keys-for-product per code. Discontinued codes are excluded by default
 *     (AC-D.6). `summary` counts the same set as the list MINUS the `state`
 *     filter, so "Verified N of M" stays honest while a state filter is applied.
 *
 *   GET /by-product/{productId}   (existing route, PR 2)
 *     gains `verification: VerificationBlock` and `values_hash` (AC-D.14), so the
 *     Specifications tab needs no second round trip. Wired in Phase 2.
 *
 * WRITES  (all perm master_data.products.edit, AC-D.15)
 *
 *   POST /verification/verify           body { product_code, values_hash }
 *     200: { product_code, outcome: 'verified'|'already_verified',
 *            verification, values_hash }
 *     409: { error: 'values_changed', values_hash: <current>, verification }
 *       or { error: 'exceptions_open', exceptions: [...] }
 *     The client echoes the hash it was shown; the handler locks the code's spec
 *     rows and compares in the same transaction (AC-D.4). The two 409s are
 *     deliberately distinguishable.
 *
 *   POST /verification/verify-bulk      body { items: [{ product_code, values_hash }] }
 *     200: { results: [{ product_code,
 *                        outcome: 'verified'|'already_verified'|'values_changed'
 *                                |'exceptions_open'|'not_found',
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
 *     Unverify has no exception gate and no hash compare (a claim is being
 *     removed, not made), lands on `unverified` rather than needs_reverify, keeps
 *     the original verified_by / verified_at on the row, and is idempotent on a
 *     code with no history (AC-D.20, AC-D.21). No reason field: AC-D.1's column
 *     list has nowhere to store one (recorded as a deliberate omission).
 *
 * THE ROW BUTTONS CALL THE BULK ROUTES
 *
 * A per-row Verify is a bulk of one (AC-D.23), so there is exactly one code path
 * to keep honest. The single routes above are the Specifications tab's, wired in
 * Phase 2.
 * ============================================================================
 */
import type {
  SpecVerificationWorklistParams,
  SpecVerificationWorklistResponse,
  UnverifyBulkResponse,
  VerifyBulkResponse,
  VerifyItem,
} from '../types/specVerification.types';
// PHASE 1 MOCK - the import and every mock body below go in Phase 2.
import {
  applyMockUnverify,
  applyMockVerify,
  fetchMockWorklist,
  MOCK_CLASS_OPTIONS,
  MOCK_LATENCY_MS,
} from '../__mocks__/specVerification.fixtures';

// PHASE 1 MOCK - swapped for apiFetch in Phase 2.
function mockDelay<T>(value: () => T): Promise<T> {
  return new Promise((resolve) => {
    setTimeout(() => resolve(value()), MOCK_LATENCY_MS);
  });
}

export async function getSpecVerificationWorklist(
  params: SpecVerificationWorklistParams,
): Promise<SpecVerificationWorklistResponse> {
  // PHASE 1 MOCK - swapped for apiFetch in Phase 2:
  //   const search = buildDataGridParams(params, {
  //     state: params.state || undefined,
  //     class_label: params.class_label || undefined,
  //     include_discontinued: params.include_discontinued ? 'true' : undefined,
  //   });
  //   const response = await apiFetch(
  //     `/api/v1/master-data/product-specifications/verification/worklist?${search}`,
  //   );
  //   if (!response.ok) {
  //     throw new Error(await extractApiError(response, 'Failed to load the verification worklist'));
  //   }
  //   return response.json();
  const switchKey = (params.searchQuery ?? '').trim().toLowerCase();
  if (switchKey === 'error') {
    await mockDelay(() => null);
    throw new Error('Failed to load the verification worklist');
  }
  if (switchKey === 'loading') {
    return new Promise<SpecVerificationWorklistResponse>(() => {});
  }
  return mockDelay(() => fetchMockWorklist(params));
}

export async function verifySpecBulk(items: VerifyItem[]): Promise<VerifyBulkResponse> {
  // PHASE 1 MOCK - swapped for apiFetch in Phase 2 (POST /verification/verify-bulk).
  return mockDelay(() => {
    const results = applyMockVerify(items);
    const verified = results.filter(
      (r) => r.outcome === 'verified' || r.outcome === 'already_verified',
    ).length;
    return { results, counts: { verified, skipped: results.length - verified } };
  });
}

export async function unverifySpecBulk(productCodes: string[]): Promise<UnverifyBulkResponse> {
  // PHASE 1 MOCK - swapped for apiFetch in Phase 2 (POST /verification/unverify-bulk).
  return mockDelay(() => {
    const results = applyMockUnverify(productCodes);
    const unverified = results.filter((r) => r.outcome === 'unverified').length;
    return { results, counts: { unverified, no_change: results.length - unverified } };
  });
}

/**
 * Class labels for the worklist's class filter.
 *
 * Phase 2 sources these from the EXISTING `GET /api/v1/master-data/spec-registry`
 * response - the `class` key carries an open vocabulary fed by
 * `product_categories.class_label` - so no new endpoint is minted for a dropdown.
 */
export async function getSpecVerificationClassOptions(): Promise<string[]> {
  // PHASE 1 MOCK - swapped for the spec-registry read in Phase 2.
  return mockDelay(() => MOCK_CLASS_OPTIONS);
}
