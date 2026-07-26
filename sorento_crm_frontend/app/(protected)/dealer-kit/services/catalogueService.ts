/**
 * Collections and bundles — API client.
 *
 * ---------------------------------------------------------------------------
 * CONTRACT — all under `/api/v1/dealer-kit`, company-scoped by the ORM filter.
 *
 * GET    /collections                          -> CollectionOut[]   page.view
 *          REUSABLE ones only. Page-scoped collections are an editor detail and
 *          would be noise here (AC-F4).
 * POST   /collections   {scope,pageId,...}     -> CollectionOut 201  page.edit
 * GET    /collections/{id}                     -> CollectionOut      page.view
 * PUT    /collections/{id}                     -> CollectionOut      page.edit
 * POST   /collections/{id}/save-as-library {name} -> CollectionOut   page.edit
 *          Promotes the SAME row, so the page stays bound to it (AC-F5).
 * DELETE /collections/{id}                     -> 204                page.edit
 * GET    /collections/{id}/resolve?showInvoicePrice=
 *                                              -> {collectionId,name,tiles[]}
 *          Tiles are resolved for the CALLING viewer. A price the viewer may
 *          not see is absent from the payload, not hidden (AC-G7).
 *
 * GET    /tile-templates                       -> TileTemplate[]     page.view
 * POST   /tile-templates {name,fields}         -> TileTemplate 201   page.edit
 * PUT    /tile-templates/{id}                  -> TileTemplate       page.edit
 * DELETE /tile-templates/{id}                  -> 204                page.edit
 *          `fields` is a WHITELIST the renderer knows how to draw; an unknown
 *          one is a 422 at authoring time rather than a blank space in print.
 *
 * GET    /bundles                              -> ResolvedBundle[]   page.view
 * POST   /bundles       {name,price,components}-> ResolvedBundle 201 page.edit
 * GET    /bundles/{id}/resolve                 -> ResolvedBundle     page.view
 * DELETE /bundles/{id}                         -> 204                page.edit
 *          `available` is derived from the components on every read and is
 *          never stored (AC-F10).
 * ---------------------------------------------------------------------------
 */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  CollectionSummary,
  ResolvedBundle,
  ResolvedCollection,
  TileField,
  TileTemplate,
} from '@/lib/dealer-kit/types';

/** Every field a tile can bind. Mirrors TILE_FIELDS on the backend. */
export const TILE_FIELDS: { value: TileField; label: string; hint: string }[] = [
  { value: 'image', label: 'Photo', hint: 'The product image' },
  { value: 'name', label: 'Name', hint: 'Product name' },
  { value: 'code', label: 'Code', hint: 'Product code' },
  { value: 'price', label: 'Price', hint: 'Resolved for whoever is reading' },
  { value: 'dimensions', label: 'Dimensions', hint: 'Length x width x height' },
  { value: 'badges', label: 'Certification badges', hint: 'Valid certifications only' },
  { value: 'cta', label: 'Action button', hint: 'Add to selection' },
];

const BASE = '/api/v1/dealer-kit';

export interface CollectionWire {
  id: string;
  scope: 'page' | 'library';
  name: string | null;
  pageId: string | null;
  conditions: Record<string, unknown> | null;
  pinnedProductIds: string[];
  excludedProductIds: string[];
  manualOrder: string[];
  memberCount: number;
  updatedAt: string;
}

export interface CollectionWrite {
  scope?: 'page' | 'library';
  pageId?: string | null;
  name?: string | null;
  conditions?: Record<string, unknown> | null;
  pinnedProductIds?: string[];
  excludedProductIds?: string[];
  manualOrder?: string[];
}

function toSummary(wire: CollectionWire): CollectionSummary {
  return {
    id: wire.id,
    name: wire.name,
    scope: wire.scope,
    memberCount: wire.memberCount,
    updatedAt: wire.updatedAt,
  };
}

export async function listCollections(): Promise<CollectionSummary[]> {
  const response = await apiFetch(`${BASE}/collections`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Could not load collections'));

  const rows: CollectionWire[] = await response.json();
  return rows.map(toSummary);
}

export async function createCollection(payload: CollectionWrite): Promise<CollectionWire> {
  const response = await apiFetch(`${BASE}/collections`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not save this product selection'));
  }
  return response.json();
}

export async function updateCollection(
  collectionId: string,
  payload: CollectionWrite,
): Promise<CollectionWire> {
  const response = await apiFetch(`${BASE}/collections/${encodeURIComponent(collectionId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not update this selection'));
  }
  return response.json();
}

export async function saveCollectionAsLibrary(
  collectionId: string,
  name: string,
): Promise<CollectionWire> {
  const response = await apiFetch(
    `${BASE}/collections/${encodeURIComponent(collectionId)}/save-as-library`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    },
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not save this as reusable'));
  }
  return response.json();
}

export async function deleteCollection(collectionId: string): Promise<void> {
  const response = await apiFetch(`${BASE}/collections/${encodeURIComponent(collectionId)}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not delete this collection'));
  }
}

export async function resolveCollection(
  collectionId: string,
  showInvoicePrice = false,
): Promise<ResolvedCollection> {
  const query = showInvoicePrice ? '?showInvoicePrice=true' : '';
  const response = await apiFetch(
    `${BASE}/collections/${encodeURIComponent(collectionId)}/resolve${query}`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not load these products'));
  }
  return response.json();
}

export async function listBundles(): Promise<ResolvedBundle[]> {
  const response = await apiFetch(`${BASE}/bundles`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Could not load bundles'));
  return response.json();
}

export async function resolveBundle(bundleId: string): Promise<ResolvedBundle> {
  const response = await apiFetch(`${BASE}/bundles/${encodeURIComponent(bundleId)}/resolve`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Could not load this bundle'));
  return response.json();
}


export async function listTileTemplates(): Promise<TileTemplate[]> {
  const response = await apiFetch(`${BASE}/tile-templates`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not load tile designs'));
  }
  return response.json();
}

export async function createTileTemplate(
  name: string,
  fields: TileField[],
): Promise<TileTemplate> {
  const response = await apiFetch(`${BASE}/tile-templates`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, fields }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not save this tile design'));
  }
  return response.json();
}

export async function updateTileTemplate(
  templateId: string,
  name: string,
  fields: TileField[],
): Promise<TileTemplate> {
  const response = await apiFetch(`${BASE}/tile-templates/${encodeURIComponent(templateId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, fields }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not update this tile design'));
  }
  return response.json();
}

export async function deleteTileTemplate(templateId: string): Promise<void> {
  const response = await apiFetch(`${BASE}/tile-templates/${encodeURIComponent(templateId)}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not delete this tile design'));
  }
}


export async function createBundle(
  name: string,
  price: string,
  components: { productId: string; quantity: number }[],
): Promise<ResolvedBundle> {
  const response = await apiFetch(`${BASE}/bundles`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, price, components }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not create this bundle'));
  }
  return response.json();
}

export async function deleteBundle(bundleId: string): Promise<void> {
  const response = await apiFetch(`${BASE}/bundles/${encodeURIComponent(bundleId)}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not delete this bundle'));
  }
}
