/**
 * Dealer Kit page builder - API contract.
 *
 * PHASE 1 STATUS: every call in this file resolves from fixtures. The contract
 * below is the deliverable, and Phase 2 must implement it exactly; any deviation
 * updates this block and the FE in the same PR.
 *
 * ---------------------------------------------------------------------------
 * CONTRACT (backend, all under `/api/v1/dealer-kit`, module-guarded on
 * `dealer_kit`, company-scoped)
 * ---------------------------------------------------------------------------
 *
 * GET    /pages                       -> { data: PageSummary[], pagination }
 *          perm: dealer_kit.page.view
 * POST   /pages                       { name, slug } -> Page
 *          perm: dealer_kit.page.edit
 * GET    /pages/{pageId}              -> Page  (doc = the `staging` version, else latest)
 *          perm: dealer_kit.page.view
 * DELETE /pages/{pageId}              -> 204   (hard delete, cascades versions + labels)
 *          perm: dealer_kit.page.edit
 *
 * POST   /pages/{pageId}/versions     { doc, commitMessage } -> PageVersion
 *          perm: dealer_kit.page.edit
 *          version = max(version)+1 PER page_id. Never updates a row in place.
 *
 * GET    /pages/{pageId}/versions     -> PageVersion[]  (newest first, labels included)
 *          perm: dealer_kit.page.view
 *
 * PUT    /pages/{pageId}/labels/{label}   { versionId } -> PageVersion
 *          label = 'published' -> perm dealer_kit.page.publish
 *          label = 'staging'   -> perm dealer_kit.page.edit
 *          Moves the label only. Busts the render cache for this page.
 *          Rollback is this same call pointed at an older versionId.
 *
 * GET    /assets                      -> { data: Asset[] }        perm: library.manage
 * POST   /assets                      { attachmentId, name, kind, tags[] } -> Asset
 * DELETE /assets/{assetId}            -> 204   409 + { usageCount } if a published page uses it
 *
 * GET    /tile-templates              -> { data: TileTemplate[] } perm: library.manage
 * POST   /tile-templates              { name, doc } -> TileTemplate
 *
 * PUBLIC (no auth, viewer-resolved):
 * GET    /public/pages/{slug}         -> { doc, resolved }  404 when no `published` label.
 *          Never falls through to the latest version (AC-B10).
 *
 * Error shape is the standard AppException envelope, read with `extractApiError`.
 */

import {
  MOCK_ASSETS,
  MOCK_PAGE,
  MOCK_PAGES,
  MOCK_TILE_TEMPLATES,
} from '../__mocks__/fixtures';
import type {
  Asset,
  Page,
  PageDoc,
  PageLabel,
  PageSummary,
  PageVersion,
  TileTemplate,
} from '@/lib/dealer-kit/types';

/** Phase-1 latency so loading states are actually exercised, not assumed. */
const MOCK_LATENCY_MS = 320;

function settle<T>(value: T, ms = MOCK_LATENCY_MS): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

export async function listPages(): Promise<PageSummary[]> {
  return settle(MOCK_PAGES);
}

export async function getPage(pageId: string): Promise<Page> {
  if (pageId !== MOCK_PAGE.id) {
    // Mirrors the real 404 so the editor's error state is reachable in Phase 1.
    await settle(null, MOCK_LATENCY_MS);
    throw new Error('Page not found');
  }
  return settle(MOCK_PAGE);
}

export async function saveVersion(
  pageId: string,
  doc: PageDoc,
  commitMessage: string,
): Promise<PageVersion> {
  const nextVersion = MOCK_PAGE.latestVersion + 1;

  return settle({
    id: `ver-${nextVersion}`,
    version: nextVersion,
    commitMessage: commitMessage || null,
    createdBy: 'You',
    createdAt: new Date().toISOString(),
    labels: [],
  });
}

export async function moveLabel(
  pageId: string,
  label: PageLabel,
  versionId: string,
): Promise<void> {
  await settle(undefined);
}

export async function listAssets(): Promise<Asset[]> {
  return settle(MOCK_ASSETS);
}

export async function listTileTemplates(): Promise<TileTemplate[]> {
  return settle(MOCK_TILE_TEMPLATES);
}
