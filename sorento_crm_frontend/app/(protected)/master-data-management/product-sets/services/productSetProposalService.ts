/**
 * Product set proposals - feature service.
 *
 * Layering: components -> hooks (useProductSetProposals) -> THIS service ->
 * lib/api-client.
 *
 * Backend contract (mounted under the `product` module guard):
 *   POST /api/v1/master-data/product-sets/proposals
 *          -> ProductSetProposalBatch. Runs the derivation over the catalogue and
 *          REPLACES the company's open batch. Codes that already exist as a set,
 *          or as a product, are not proposed.   gated `master_data.product_sets.edit`
 *   GET  /api/v1/master-data/product-sets/proposals
 *          -> { batch: ProductSetProposalBatch | null }. Null means no pass has
 *          run yet, which is not the same as a pass that found nothing.
 *                                              gated `master_data.product_sets.view`
 *   POST /api/v1/master-data/product-sets/proposals/apply
 *          body { proposal_ids: string[] } -> ApplyProposalsResult
 *          Names IDS only. The set code and its members come off the stored
 *          proposal, never off the payload, so the screen cannot write a set the
 *          pass did not derive.               gated `master_data.product_sets.edit`
 *
 * The pass WRITES NOTHING. Applying is the only path onto `product_sets`, and it
 * goes through the same service the Add-set modal uses.
 *
 * Both proposal routes are declared BEFORE `/{product_set_id}` on the backend
 * router. Declared the other way round, the UUID path param swallows
 * `/proposals` and this screen gets "Product set not found" instead of a batch.
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  ApplyProposalsResult,
  ProductSetProposal,
  ProductSetProposalBatch,
} from '../types/productSetProposal.types';

const BASE = '/api/v1/master-data/product-sets/proposals';

/**
 * Money and quantities arrive as STRINGS.
 *
 * The API serialises `Decimal` as a string, so `1180.00` reaches us as `"1180.00"`.
 * `String.prototype.toLocaleString` exists and returns the string untouched, so a
 * component formatting it gets `RM 1180.00` with no thousands separator and no
 * error anywhere - it looked right against the mock, which used real numbers.
 * Coerced once here, at the boundary, so no component has to remember.
 */
function num(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizeProposal(proposal: ProductSetProposal): ProductSetProposal {
  return {
    ...proposal,
    computed_price: num(proposal.computed_price),
    members: (proposal.members ?? []).map((m) => ({
      ...m,
      list_price: num(m.list_price),
      quantity: num(m.quantity) ?? 1,
    })),
  };
}

function normalizeBatch(batch: ProductSetProposalBatch | null): ProductSetProposalBatch | null {
  if (!batch) return null;
  return { ...batch, proposals: (batch.proposals ?? []).map(normalizeProposal) };
}

export async function getProductSetProposals(): Promise<ProductSetProposalBatch | null> {
  const response = await apiFetch(BASE);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load proposals'));
  }
  // The envelope carries an explicit null: no pass has ever run, which the empty
  // state says differently from a pass that found nothing.
  const body = await response.json();
  return normalizeBatch(body?.batch ?? null);
}

export async function runProductSetProposals(): Promise<ProductSetProposalBatch> {
  const response = await apiFetch(BASE, { method: 'POST' });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to scan the catalogue'));
  }
  return normalizeBatch(await response.json()) as ProductSetProposalBatch;
}

export async function applyProductSetProposals(
  proposalIds: string[],
): Promise<ApplyProposalsResult> {
  const response = await apiFetch(`${BASE}/apply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ proposal_ids: proposalIds }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to create the sets'));
  }
  // A refusal is part of a 200: the other ticked candidates still landed, and
  // the reviewer is told per set which did not.
  return response.json();
}
