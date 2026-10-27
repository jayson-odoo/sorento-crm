/**
 * Catalogue photo readings (CATALOG-IMAGES): upload a supplier catalogue PDF, review the photos the
 * worker cut out of it, attach them to products. Contract: PLAN-catalog-image-extract-27oct.md "API".
 *
 * Phase 1 runs on the in-memory mock behind `USE_MOCK`. S3 deletes the switch and the mock module.
 */

import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { DataGridApiResponse } from '@/components/ui/data-grid';
import { catalogPhotoMock } from './catalogPhotoReadingService.mock';

const USE_MOCK = true;

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
}

export interface CatalogPhoto {
  id: string;
  page: number;
  position: number;
  thumbnail_url: string;
  image_url: string;
  printed_code: string | null;
  block_codes: string[];
  placeholders: string[];
  product: ProductRef | null;
  rung: 'exact' | 'normalised' | 'suffix' | 'alias' | 'none' | null;
  confidence: CatalogPhotoConfidence;
  suggestion: string | null;
  other_block_products: ProductRef[];
  also_attach_product_ids: string[];
  duplicate: { attachment_id: string; thumbnail_url: string; distance: number } | null;
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
  if (USE_MOCK) return catalogPhotoMock.upload(file);
  const body = new FormData();
  body.append('file', file);
  const response = await apiFetch(BASE, { method: 'POST', body });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not read that catalogue'));
  }
  return response.json();
}

export async function getCatalogPhotoReading(id: string): Promise<CatalogPhotoReading> {
  if (USE_MOCK) return catalogPhotoMock.get(id);
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
  if (USE_MOCK) return catalogPhotoMock.list(id, params);
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
  /** Mock only (the real API answers with the product itself); S3 drops it with the mock. */
  pickedProductCode?: string,
): Promise<CatalogPhoto> {
  if (USE_MOCK) return catalogPhotoMock.patch(id, photoId, patch, pickedProductCode);
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
  if (USE_MOCK) return catalogPhotoMock.attach(id);
  const response = await apiFetch(`${BASE}/${id}/attach`, { method: 'POST' });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not attach the photos'));
  }
  return response.json();
}
