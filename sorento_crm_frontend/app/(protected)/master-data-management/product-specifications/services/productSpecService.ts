/**
 * ============================================================================
 * API CONTRACT - the editable spec table (PR 2)
 * ============================================================================
 *
 * Written out here because the frontend was built against it before any of it
 * existed (Phase 1), and because milestone 2's supplier portal renders the same
 * components against a different principal and has to match it.
 *
 * READS
 *
 *   GET /api/v1/master-data/product-specifications/by-product/{productId}
 *     -> ProductSpecDetail. `spec.values` is the table's row set; `spec.provenance`
 *        stamps each row with its source. A removed key appears ONLY in
 *        `provenance`, as `{source: 'human', absent: true}` with no entry in
 *        `values` - that tombstone is what stops re-derivation refilling it, and
 *        the table deliberately renders no row for it (removed means gone). The
 *        add picker offers it again; setting a value replaces the stamp.
 *     -> `exceptions[]` carries `reason: 'human_override_conflict'` with
 *        `proposed` = what the rules now read. Answered by SETTING THE VALUE;
 *        there is no resolve endpoint and there is not meant to be one (D9).
 *
 *   GET /api/v1/master-data/spec-registry
 *     -> { keys: SpecRegistryKey[] }, vocabulary already merged.
 *
 *   GET /api/v1/master-data/spec-registry/applicable-keys?code={productCode}
 *     -> { code, keys: [{ spec_key, label, data_type, unit, allowed_values,
 *          synonyms, applicable, held }] }
 *        `applicable` mirrors derivation's `applies_when` gate; `held` counts a
 *        tombstone as held. 404 on an unknown code - deliberately not an empty
 *        list, which would read as "this product may carry nothing".
 *
 *   GET /api/v1/master-data/spec-registry/similar?label={label}
 *     -> { label, match: { spec_key, label, matched_on, matched_text } | null }
 *        `matched_on` is one of spec_key | label | synonym.
 *
 * WRITES
 *
 *   PUT    .../by-product/{productId}/values/{specKey}   body { value }
 *   DELETE .../by-product/{productId}/values/{specKey}?mode=absent|revert
 *     `absent` = "this product does not have this spec", survives re-derivation.
 *     `revert` = hand the key back to the rules.
 *
 *   POST  /api/v1/master-data/spec-registry            (create a key)
 *   PATCH /api/v1/master-data/spec-registry/{specKey}  (add a word to a key)
 *
 * THE 422 THAT IS NOT AN ERROR ENVELOPE
 *
 * Both writes above refuse a near-duplicate with a TOP-LEVEL body, not the
 * AppException envelope, because the client has to render WHICH existing thing it
 * collided with:
 *
 *     422 { error: string, match: {...}, acknowledge_field: 'acknowledge_similar' }
 *
 * Resending with `acknowledge_similar: true` is what gets through. `extractApiError`
 * cannot read this - it is string-only - so these two calls parse the body
 * themselves and throw a `SpecSimilarError` carrying the match.
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { SimilarKeyMatch, SpecDataType } from '@/components/spec-table';
import type {
  FindabilityResult,
  FindabilityRun,
  SpecDerivationRule,
  SpecSearchPolicyRow,
  ProductSpecDetail,
  ProductSpecRow,
  SpecException,
  SpecPreviewResult,
  SpecRegistryKey,
} from '../types/productSpec.types';

interface Paged<T> {
  data: T[];
  pagination: { total: number; page: number; limit: number };
}

export async function getProductSpecs(params: {
  page?: number;
  limit?: number;
  query?: string;
  status?: string;
}): Promise<Paged<ProductSpecRow>> {
  const search = new URLSearchParams({
    page: String(params.page ?? 1),
    limit: String(params.limit ?? 25),
    ...(params.query ? { query: params.query } : {}),
    ...(params.status ? { status: params.status } : {}),
  });

  const response = await apiFetch(
    `/api/v1/master-data/product-specifications/?${search.toString()}`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load product specifications'));
  }
  return response.json();
}

export async function getSpecExceptions(params: {
  page?: number;
  limit?: number;
}): Promise<Paged<SpecException>> {
  const search = new URLSearchParams({
    page: String(params.page ?? 1),
    limit: String(params.limit ?? 25),
  });

  const response = await apiFetch(
    `/api/v1/master-data/product-specifications/exceptions?${search.toString()}`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load spec exceptions'));
  }
  return response.json();
}

/**
 * One product's derived specs, or the reason there are none. Used by the
 * Specifications tab on the product record.
 */
export async function getProductSpecDetail(productId: string): Promise<ProductSpecDetail> {
  const response = await apiFetch(
    `/api/v1/master-data/product-specifications/by-product/${productId}`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load derived specifications'));
  }
  return response.json();
}

export async function getSpecRegistry(): Promise<{ keys: SpecRegistryKey[] }> {
  const response = await apiFetch('/api/v1/master-data/spec-registry');
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load the spec registry'));
  }
  return response.json();
}

/**
 * Run the ranker exactly as the chatbot would. Returns each candidate's score and the
 * keys it matched on, so a reviewer can see why a result placed where it did.
 */
export async function previewSpecSearch(body: {
  specs: { key: string; value: string | number }[];
  free_terms: string[];
  floor?: number;
  /** The raw sentence, read semantically. */
  phrase?: string;
  /** False to see the literal reading alone, for comparison. */
  understand?: boolean;
}): Promise<SpecPreviewResult> {
  const response = await apiFetch('/api/v1/master-data/product-specifications/preview-search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Spec search preview failed'));
  }
  return response.json();
}

/** One key as the add-a-specification picker needs it: may it, and does it already. */
export interface ApplicableSpecKey {
  spec_key: string;
  label: string;
  data_type: string;
  unit: string | null;
  allowed_values: string[];
  synonyms: Record<string, string[]>;
  /** The `applies_when` gate, evaluated the way derivation evaluates it. */
  applicable: boolean;
  /** Already on the product. A tombstone counts: it is on the table with a revert. */
  held: boolean;
}

/**
 * Which keys this product MAY carry, and which it already does.
 *
 * Not `getKeysForProduct`, which answers from the values the product already holds -
 * the numerator where the picker needs the denominator.
 */
export async function getApplicableSpecKeys(
  productCode: string,
): Promise<{ code: string; keys: ApplicableSpecKey[] }> {
  const response = await apiFetch(
    `/api/v1/master-data/spec-registry/applicable-keys?code=${encodeURIComponent(productCode)}`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load the specifications'));
  }
  return response.json();
}

/** The existing key a proposed label already means, or null when it is genuinely new. */
export async function getSimilarSpecKey(label: string): Promise<SimilarKeyMatch | null> {
  const response = await apiFetch(
    `/api/v1/master-data/spec-registry/similar?label=${encodeURIComponent(label)}`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to check the name'));
  }
  return (await response.json()).match ?? null;
}

/**
 * The server refused a near-duplicate and said which existing thing it collided with.
 *
 * Its own error type because the caller has to do something with `match` - offer the
 * existing word - which a message string cannot carry. `extractApiError` is string-only
 * and would flatten exactly the part that matters.
 */
export class SpecSimilarError extends Error {
  readonly match: Record<string, unknown>;

  constructor(message: string, match: Record<string, unknown>) {
    super(message);
    this.name = 'SpecSimilarError';
    this.match = match;
  }
}

/**
 * Raise the near-duplicate refusal as itself, and anything else as a plain error.
 *
 * `extractApiError` is still what handles every ordinary failure below; this reads the
 * body first ONLY for the 422 shape it cannot represent, because that response's whole
 * payload is the `match` object and a string would throw it away.
 */
async function throwSpecWriteError(response: Response, fallback: string): Promise<never> {
  if (response.status === 422) {
    let body: { error?: string; match?: Record<string, unknown> } | null = null;
    try {
      body = await response.clone().json();
    } catch {
      body = null;
    }
    if (body?.match) {
      throw new SpecSimilarError(String(body.error ?? fallback), body.match);
    }
  }
  throw new Error(await extractApiError(response, fallback));
}

/** Register a new spec key. Owned by whoever creates it — never seed-repaired. */
export async function createSpecKey(body: {
  spec_key: string;
  label: string;
  data_type: SpecDataType | string;
  unit?: string | null;
  allowed_values?: string[];
  user_synonyms?: Record<string, string[]>;
  rank_weight?: number;
  is_active?: boolean;
  /** Resend with true to get past the server's near-duplicate refusal. */
  acknowledge_similar?: boolean;
}): Promise<SpecRegistryKey> {
  const response = await apiFetch('/api/v1/master-data/spec-registry', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    await throwSpecWriteError(response, 'Failed to create the spec key');
  }
  return response.json();
}

/**
 * Add a word to a key's vocabulary, from the product page.
 *
 * A separate call rather than `updateSpecKey` with one field, because the two are
 * different permissions: this is `master_data.products.edit` (a merchandiser
 * correcting a spec), while everything else on that route needs
 * `master_data.spec_registry.edit`. Naming it separately is what keeps the caller
 * from quietly widening its own payload.
 */
export async function addValueToSpecKey(
  specKey: string,
  userValues: string[],
  options: { acknowledgeSimilar?: boolean } = {},
): Promise<SpecRegistryKey> {
  const response = await apiFetch(`/api/v1/master-data/spec-registry/${specKey}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_values: userValues,
      ...(options.acknowledgeSimilar ? { acknowledge_similar: true } : {}),
    }),
  });
  if (!response.ok) {
    await throwSpecWriteError(response, 'Failed to add the value');
  }
  return response.json();
}

/**
 * Edit calibration and extend vocabulary. A seeded key's `allowed_values` are
 * rejected by the API on purpose — they are the chatbot parser's contract.
 */
export async function updateSpecKey(
  specKey: string,
  body: {
    label?: string;
    rank_weight?: number;
    is_active?: boolean;
    match_tolerance?: number;
    match_decay?: number;
    user_synonyms?: Record<string, string[]>;
    suppressed_synonyms?: Record<string, string[]>;
    allowed_values?: string[];
    excluded_values?: string[];
    value_weights?: Record<string, number>;
    user_values?: string[];
    suppressed_values?: string[];
    derivation_rules?: SpecDerivationRule[];
    applies_when?: Record<string, string[]>;
  },
): Promise<SpecRegistryKey> {
  const response = await apiFetch(`/api/v1/master-data/spec-registry/${specKey}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to save the spec key'));
  }
  return response.json();
}

/** One spec a given product carries, and where it was read from. */
export interface ProductSpecKey {
  value: string | number | boolean | null;
  source: string | null;
}

/**
 * Which spec keys a product code carries, so the keys table can be filtered by product.
 * `matched_product` is null when the code names nothing.
 */
export async function getKeysForProduct(code: string): Promise<{
  code: string;
  matched_product: { id: string; product_code: string } | null;
  keys: Record<string, ProductSpecKey>;
}> {
  const response = await apiFetch(
    `/api/v1/master-data/spec-registry/keys-for-product?code=${encodeURIComponent(code)}`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to look up the product'));
  }
  return response.json();
}

/** Every product carrying a key, with the words each value was read from. */
export interface SpecKeyProduct {
  id: string;
  product_code: string;
  description: string | null;
  class: string | null;
  value: string | number | boolean | null;
  source: string | null;
  evidence: string | null;
}

export interface SpecKeyProducts {
  spec_key: string;
  label: string;
  total: number;
  by_value: { value: string | null; count: number }[];
  by_class: { class: string | null; count: number }[];
  by_source: { source: string | null; count: number }[];
  products: SpecKeyProduct[];
}

/** How many products carry each key right now. Not `measured_coverage`. */
export async function getSpecCoverage(): Promise<{ coverage: Record<string, number> }> {
  const response = await apiFetch('/api/v1/master-data/spec-registry/coverage');
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load the coverage'));
  }
  return response.json();
}

export async function getSpecKeyProducts(
  specKey: string,
  params: { value?: string; q?: string; limit?: number; offset?: number } = {},
): Promise<SpecKeyProducts> {
  const query = new URLSearchParams();
  if (params.value !== undefined) query.set('value', params.value);
  // Searched server-side over the whole key, not over the page on screen.
  if (params.q) query.set('q', params.q);
  query.set('limit', String(params.limit ?? 100));
  query.set('offset', String(params.offset ?? 0));
  const response = await apiFetch(
    `/api/v1/master-data/spec-registry/${specKey}/products?${query.toString()}`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load the products'));
  }
  return response.json();
}

/** Read one product again with the rules that are live now. */
export async function rederiveProduct(productId: string): Promise<{ written: number }> {
  const response = await apiFetch(
    `/api/v1/master-data/product-specifications/by-product/${productId}/rederive`,
    { method: 'POST' },
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not read this product again'));
  }
  return response.json();
}

/** Set a value the catalogue never states. Held against every later re-derivation. */
export async function setSpecValueByHand(
  productId: string,
  specKey: string,
  value: string | number | boolean,
): Promise<void> {
  const response = await apiFetch(
    `/api/v1/master-data/product-specifications/by-product/${productId}/values/${specKey}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ value }),
    },
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not save the value'));
  }
}

/**
 * Correct the flyer card this product's specs are read from, and read it again.
 *
 * The card text comes from a machine reading of the printed flyer, and that reading
 * missed cards. Sending an empty string means the product has no flyer card at all.
 */
export async function setFlyerText(
  productId: string,
  text: string,
): Promise<{ flyer_text: string | null }> {
  const response = await apiFetch(
    `/api/v1/master-data/product-specifications/by-product/${productId}/flyer-text`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    },
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not save the flyer text'));
  }
  return response.json();
}

/**
 * Take a value away, one of the two ways, because they mean different things.
 *
 * `revert` hands the key back to derivation and it comes back with whatever the
 * catalogue says. `absent` is a statement of fact - this product does not have this
 * spec - and it survives every later run as a tombstone rather than being filled in
 * again. `revert` is the default because it is what the shipped screen always did.
 */
export async function clearSpecValueByHand(
  productId: string,
  specKey: string,
  mode: 'revert' | 'absent' = 'revert',
): Promise<void> {
  const response = await apiFetch(
    `/api/v1/master-data/product-specifications/by-product/${productId}/values/${specKey}?mode=${mode}`,
    { method: 'DELETE' },
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not clear the value'));
  }
}

export async function deleteSpecKey(specKey: string): Promise<void> {
  const response = await apiFetch(`/api/v1/master-data/spec-registry/${specKey}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to delete the spec key'));
  }
}


/** Every scoring knob the ranker reads, with its shipped default alongside. */
export async function getSearchPolicy(): Promise<{ policy: SpecSearchPolicyRow[] }> {
  const response = await apiFetch('/api/v1/master-data/spec-registry/policy');
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load the search settings'));
  }
  return response.json();
}

export async function updateSearchPolicy(
  policyKey: string,
  value: number,
): Promise<{ policy_key: string; value: number }> {
  const response = await apiFetch(`/api/v1/master-data/spec-registry/policy/${policyKey}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ value }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to save the search setting'));
  }
  return response.json();
}


export interface CatalogueStatus {
  status: 'idle' | 'running' | 'done' | 'failed';
  started_at: string | null;
  finished_at: string | null;
  result: { codes?: number; written?: number; error?: string } | null;
  /** The rules have been edited since the stored specifications were read. */
  rules_changed_since_last_read: boolean;
  ever_read: boolean;
}

export async function getCatalogueStatus(): Promise<CatalogueStatus> {
  const response = await apiFetch('/api/v1/master-data/spec-registry/catalogue-status');
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to read the catalogue status'));
  }
  return response.json();
}

/** Re-read every product with the rules as they stand now. Runs in the background. */
export async function rereadCatalogue(): Promise<{ status: string }> {
  const response = await apiFetch('/api/v1/master-data/spec-registry/reread-catalogue', {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to start reading the catalogue'));
  }
  return response.json();
}

// --- Findability: can a customer find this product by describing it? ---------------

export async function getFlyers(): Promise<{
  flyers: { source_id: string; source_label: string; cards: number; last_run: string | null }[];
}> {
  const response = await apiFetch(
    '/api/v1/master-data/product-specifications/findability/flyers',
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load flyers'));
  }
  return response.json();
}

export async function runFindability(params: {
  sourceId?: string;
  window?: number;
  limit?: number;
}): Promise<FindabilityRun> {
  const search = new URLSearchParams({
    ...(params.sourceId ? { source_id: params.sourceId } : {}),
    ...(params.window ? { window: String(params.window) } : {}),
    ...(params.limit ? { limit: String(params.limit) } : {}),
  });
  const response = await apiFetch(
    `/api/v1/master-data/product-specifications/findability/run?${search.toString()}`,
    { method: 'POST' },
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to run the findability sweep'));
  }
  return response.json();
}

export async function getFindabilityRuns(
  sourceId?: string,
): Promise<{ runs: FindabilityRun[] }> {
  const search = new URLSearchParams(sourceId ? { source_id: sourceId } : {});
  const response = await apiFetch(
    `/api/v1/master-data/product-specifications/findability/runs?${search.toString()}`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load past sweeps'));
  }
  return response.json();
}

export async function getFindabilityRun(
  runId: string,
  params: { boundary?: string; q?: string } = {},
): Promise<{ run: FindabilityRun; results: FindabilityResult[] }> {
  const search = new URLSearchParams({
    ...(params.boundary ? { boundary: params.boundary } : {}),
    ...(params.q ? { q: params.q } : {}),
  });
  const response = await apiFetch(
    `/api/v1/master-data/product-specifications/findability/runs/${runId}?${search.toString()}`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load the sweep'));
  }
  return response.json();
}
