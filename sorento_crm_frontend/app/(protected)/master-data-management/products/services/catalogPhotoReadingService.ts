/**
 * Catalogue photo readings (CATALOG-IMAGES): upload a supplier catalogue PDF, review the photos the
 * worker cut out of it, attach them to products. Contract: PLAN-catalog-image-extract-27oct.md "API".
 *
 */

import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { DataGridApiResponse } from '@/components/ui/data-grid';

const BASE = '/api/v1/master-data/catalogue-photo-readings';

export type CatalogPhotoReadingStatus = 'queued' | 'reading' | 'ready' | 'failed';
export type CatalogPhotoTab = 'ready' | 'duplicate' | 'needs_product' | 'skipped';
export type CatalogPhotoDecision = 'attach' | 'skip' | 'keep_both' | 'replace';
export type CatalogPhotoConfidence = 'high' | 'medium' | 'low' | 'none';

export interface ProductRef {
  id: string;
  product_code: string;
}

export interface CatalogPhotoCounts {
  ready: number;
  duplicate: number;
  needs_product: number;
  skipped: number;
  to_attach: number;
}

export interface CatalogPhotoReading {
  id: string;
  file_name: string;
  status: CatalogPhotoReadingStatus;
  page_count: number | null;
  photo_count: number | null;
  error: string | null;
  directory_id: string | null;
  created_at: string;
  created_by_name: string | null;
  counts: CatalogPhotoCounts;
  /** Rows already linked to a product; the Attach step reads as done once this is above 0. */
  attached_count: number;
}

export interface CatalogPhoto {
  id: string;
  page: number;
  position: number;
  thumbnail_url: string | null;
  image_url: string | null;
  printed_code: string | null;
  block_codes: string[];
  placeholders: string[];
  product: ProductRef | null;
  rung: 'exact' | 'normalised' | 'suffix' | 'alias' | 'manual' | 'none' | null;
  confidence: CatalogPhotoConfidence;
  suggestion: string | null;
  other_block_products: ProductRef[];
  also_attach_product_ids: string[];
  duplicate: { attachment_id: string; thumbnail_url: string | null; distance: number } | null;
  decision: CatalogPhotoDecision;
  attached_at: string | null;
}

export interface CatalogPhotosParams {
  tab: CatalogPhotoTab;
  pageIndex: number;
  pageSize: number;
  sort?: string;
  desc?: boolean;
}

export interface CatalogPhotoPatch {
  product_id?: string | null;
  decision?: CatalogPhotoDecision;
  also_attach_product_ids?: string[];
}

export interface CatalogPhotoAttachResult {
  attached: number;
  replaced: number;
  skipped: number;
  products: number;
}

export async function uploadCatalogPhotoReading(file: File): Promise<CatalogPhotoReading> {
  const body = new FormData();
  body.append('file', file);
  const response = await apiFetch(BASE, { method: 'POST', body });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not read that catalogue'));
  }
  return response.json();
}

export async function getCatalogPhotoReading(id: string): Promise<CatalogPhotoReading> {
  const response = await apiFetch(`${BASE}/${id}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not load the catalogue reading'));
  }
  return response.json();
}

export async function listCatalogPhotos(
  id: string,
  params: CatalogPhotosParams,
): Promise<DataGridApiResponse<CatalogPhoto>> {
  const search = buildDataGridParams(
    {
      pageIndex: params.pageIndex,
      pageSize: params.pageSize,
      sorting: params.sort ? [{ id: params.sort, desc: Boolean(params.desc) }] : [],
    },
    { tab: params.tab },
  );
  const response = await apiFetch(`${BASE}/${id}/photos?${search.toString()}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not load the photos'));
  }
  return response.json();
}

export async function patchCatalogPhoto(
  id: string,
  photoId: string,
  patch: CatalogPhotoPatch,
): Promise<CatalogPhoto> {
  const response = await apiFetch(`${BASE}/${id}/photos/${photoId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not update that photo'));
  }
  return response.json();
}

export async function attachCatalogPhotos(id: string): Promise<CatalogPhotoAttachResult> {
  const response = await apiFetch(`${BASE}/${id}/attach`, { method: 'POST' });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not attach the photos'));
  }
  return response.json();
}
