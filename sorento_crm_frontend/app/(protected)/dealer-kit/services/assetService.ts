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
 * ```
 *
 * Both endpoints are gated on `dealer_kit.library.manage`.
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
