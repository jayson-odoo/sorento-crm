/**
 * The Selection: what somebody chose, and the room they put it in.
 *
 * Every number here comes from the server, resolved for whoever is asking -
 * price, availability, dimensions, the total. The designer does no pricing
 * arithmetic and stores no price, which is what stops a quote disagreeing with
 * the catalogue it came from.
 *
 * CONTRACT
 *   POST   /api/v1/dealer-kit/selections                          -> Selection
 *   GET    /api/v1/dealer-kit/selections/{id}                     -> Selection
 *   PUT    /api/v1/dealer-kit/selections/{id}       { name }      -> Selection
 *   DELETE /api/v1/dealer-kit/selections/{id}                     -> 204
 *   POST   /api/v1/dealer-kit/selections/{id}/lines
 *            { productId, quantity }  (ABSOLUTE, 0 removes)       -> Selection
 *   DELETE /api/v1/dealer-kit/selections/{id}/lines/{productId}   -> Selection
 *   PUT    /api/v1/dealer-kit/selections/{id}/room
 *            { outline, placements, openings, ceilingHeightMm }   -> Selection
 *   POST   /api/v1/dealer-kit/selections/{id}/quote
 *            { excludedProductIds }                               -> Quote
 *
 * Every mutation returns the WHOLE selection, so the client never has to merge
 * a partial response into local state and never has to guess what a write did
 * to the total.
 */

import type { Finishes } from '@/lib/dealer-kit/finishes';
import type { Opening } from '@/lib/dealer-kit/roomOpenings';

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

export interface SelectionLine {
  lineId: string;
  productId: string;
  productCode: string | null;
  productName: string;
  quantity: number;
  price: string | null;
  /** Absent unless the viewer is entitled to it - not merely hidden. */
  invoicePrice: string | null;
  lineTotal: string | null;
  /** Millimetres, or null when the catalogue has no dimensions for it. */
  dimensionsMm: { length: number; width: number; height: number } | null;
  isAvailable: boolean;
  unavailableReason: string | null;
}

export interface RoomPlacement {
  lineId: string;
  productId: string;
  x: number;
  y: number;
  rotation: number;
}

export interface Room {
  outline: { x: number; y: number }[];
  placements: RoomPlacement[];
  /** Doors and windows. Holes in walls, never priced. */
  openings?: Opening[];
  /** Surface finishes, by id. */
  finishes?: Finishes | null;
  /** Floor to ceiling, in millimetres. Absent on designs saved before it existed. */
  ceilingHeightMm?: number | null;
}

export interface Selection {
  id: string;
  name: string | null;
  currency: string;
  lines: SelectionLine[];
  total: string | null;
  unavailableCount: number;
  room: Room | null;
  /** Derived from the outline on every read, never stored. */
  roomAreaSqm: number | null;
}

const BASE = '/api/v1/dealer-kit/selections';

async function read(response: Response, fallback: string): Promise<Selection> {
  if (!response.ok) throw new Error(await extractApiError(response, fallback));
  return (await response.json()) as Selection;
}

export async function createSelection(name?: string): Promise<Selection> {
  const response = await apiFetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: name ?? null }),
  });
  return read(response, 'Could not start a design');
}

export async function getSelection(selectionId: string): Promise<Selection> {
  return read(await apiFetch(`${BASE}/${selectionId}`), 'Could not load this design');
}

export async function renameSelection(selectionId: string, name: string): Promise<Selection> {
  const response = await apiFetch(`${BASE}/${selectionId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  return read(response, 'Could not rename this design');
}

export async function deleteSelection(selectionId: string): Promise<void> {
  const response = await apiFetch(`${BASE}/${selectionId}`, { method: 'DELETE' });
  if (!response.ok) throw new Error(await extractApiError(response, 'Could not delete this design'));
}

/** Set a product to an absolute quantity. Zero removes it. */
export async function setSelectionLine(
  selectionId: string,
  productId: string,
  quantity: number,
): Promise<Selection> {
  const response = await apiFetch(`${BASE}/${selectionId}/lines`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ productId, quantity }),
  });
  return read(response, 'Could not update the products in this design');
}

export async function saveRoom(selectionId: string, room: Room): Promise<Selection> {
  const response = await apiFetch(`${BASE}/${selectionId}/room`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(room),
  });
  return read(response, 'Could not save the room');
}

export interface QuoteLine extends SelectionLine {
  /** False when the dealer left it off, or when it cannot be sold at all. */
  included: boolean;
}

export interface Quote {
  id: string;
  name: string | null;
  currency: string;
  lines: QuoteLine[];
  /** What the included lines come to. Computed by the SERVER, never here. */
  subtotal: string;
  /** Everything available, for comparison. */
  total: string | null;
  excludedCount: number;
}

/**
 * The design as a figure somebody can hand to a customer.
 *
 * A POST because it carries a body, not because it writes: the excluded list
 * is a question, and asking twice gives the same answer.
 */
export async function getQuote(
  selectionId: string,
  excludedProductIds: string[] = [],
): Promise<Quote> {
  const response = await apiFetch(`${BASE}/${selectionId}/quote`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ excludedProductIds }),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Could not build the quote'));
  return response.json();
}
