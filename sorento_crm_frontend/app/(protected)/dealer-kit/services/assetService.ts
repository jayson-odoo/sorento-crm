/**
 * The Dealer Kit artwork library: badges, icons, diagrams, logos and fonts.
 *
 * ## API contract
 *
 * ```
 * GET  /api/v1/dealer-kit/assets?kind=&tag=&q=&limit=
 *   200 [{ id, name, kind, tags[], url, mime_type }]
 *   `url` is null when the file cannot be signed - absent, not broken.
 *
 * POST /api/v1/dealer-kit/assets            multipart/form-data
 *   file, kind, name?, tags?  (tags = comma separated)
 *   201 { id, name, kind, tags[], url, mime_type }
 *   422 when the extension does not match the kind (a font must be
 *       .woff2/.ttf/.otf; artwork must be .png/.jpg/.webp/.svg).
 *
 * PATCH /api/v1/dealer-kit/assets/{id}       { name }
 *   200 { id, name, kind, tags[], url, mime_type }
 *   409 FONT_NAME_TAKEN - another font already carries that name.
 *   Renaming a font also rewrites every layer that named the old family;
 *   anything else changes only the row.
 *
 * DELETE /api/v1/dealer-kit/assets/{id}
 *   204, or 409 FONT_IN_USE / ASSET_IN_USE naming what still uses it. No
 *   service function here for it: delete is a deferred action (D7) parked
 *   through `pendingActionService.createPendingAction` with
 *   `actionKey: 'dealer_kit_asset.delete'` - this route is only the
 *   immediate one the record action executes, for API/non-UI callers.
 * ```
 *
 * All four endpoints are gated on `dealer_kit.library.manage`.
 */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

const BASE = '/api/v1/dealer-kit/assets';

export type AssetKind = 'decorative' | 'badge' | 'icon' | 'diagram' | 'logo' | 'font';

export interface KitAsset {
  id: string;
  name: string;
  kind: string;
  tags: string[];
  url: string | null;
  mime_type: string | null;
}

export interface ListAssetsParams {
  kind?: AssetKind | string;
  tag?: string;
  query?: string;
  limit?: number;
}

export async function listAssets(params: ListAssetsParams = {}): Promise<KitAsset[]> {
  const usp = new URLSearchParams();
  if (params.kind) usp.set('kind', params.kind);
  if (params.tag) usp.set('tag', params.tag);
  if (params.query?.trim()) usp.set('q', params.query.trim());
  if (params.limit) usp.set('limit', String(params.limit));

  const qs = usp.toString();
  const response = await apiFetch(qs ? `${BASE}?${qs}` : BASE);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load the asset library'));
  }
  return response.json();
}

export async function uploadAsset(input: {
  file: File;
  kind: AssetKind;
  name?: string;
  tags?: string[];
}): Promise<KitAsset> {
  const form = new FormData();
  form.append('file', input.file);
  form.append('kind', input.kind);
  if (input.name) form.append('name', input.name);
  if (input.tags?.length) form.append('tags', input.tags.join(','));

  // No Content-Type header: the browser sets the multipart boundary itself, and
  // setting it by hand produces a body the server cannot parse.
  const response = await apiFetch(BASE, { method: 'POST', body: form });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to upload the file'));
  }
  return response.json();
}

/** The company's brand fonts, for the inspector list and `@font-face`. */
export async function listFontAssets(): Promise<KitAsset[]> {
  return listAssets({ kind: 'font', limit: 100 });
}

/**
 * Rename a library asset. For a font this also rewrites every layer that
 * named the old family, in the same backend transaction - nothing further
 * to do here beyond telling the caller the old name, so it can rewrite the
 * OPEN document's layers too (see `TagCanvasEditor`'s `onRenamed`).
 */
export async function renameAsset(id: string, name: string): Promise<KitAsset> {
  const response = await apiFetch(`${BASE}/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to rename the asset'));
  }
  return response.json();
}

/**
 * The same-origin URL `FontFace.load()` fetches an asset's bytes from.
 *
 * Built from the asset id rather than read off `KitAsset.url`: that field is a
 * signed CDN link with no CORS header on some hosts, which `FontFace.load()`
 * rejects outright (price-tag-r4 S1). `/api/v1/public/dealer-kit/fonts/{id}`
 * is unauthenticated and same-origin, so there is nothing to sign and nothing
 * for CORS to block.
 *
 * BARE, with no `NEXT_PUBLIC_API_URL` prefix. That value is inlined into the
 * browser bundle at build time, so it names a host as the BROWSER's machine
 * sees it, which is why `apiFetch` (`lib/api.ts`) strips it for every
 * browser-side call. The page's own origin already proxies `/api/v1` to the
 * backend - Next's rewrite in dev, nginx in production - so the relative path
 * is both correct and the only one that cannot point at the wrong machine.
 * The print page is the one caller that must prefix it, because the PDF
 * worker drives that page directly rather than through the proxy.
 */
export function fontAssetUrl(assetId: string): string {
  return `/api/v1/public/dealer-kit/fonts/${assetId}`;
}
