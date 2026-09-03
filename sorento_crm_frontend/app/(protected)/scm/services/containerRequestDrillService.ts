/**
 * The documents behind the SPO / Incoming PL / PO figures on a loading-plan row.
 *
 * `PLAN-scm-fulfilment-feedback-p4.md` R8, AC-B4/AC-B5. One endpoint, three kinds, because
 * the backend answers all three from the predicates the CELLS sum - so `total` is the number
 * that opened the dialog, not a second reading of it.
 *
 * `on_hand` is deliberately not a kind here: that lightbox is served by
 * `/reorder-runs/location-stock?product_id=` through `useLocationStock`, which already
 * answers it per product and is reused as-is.
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

export type ContainerRequestDrillKind = 'spo' | 'incoming_pl' | 'po';

/** One shipping order on the water for a site pool (Open), or one that landed (History). */
export interface ContainerRequestDrillSpoRow {
  spo_number: string | null;
  /** Null on an allocation nobody has put on a shipment yet - it is still on order, so the
   *  cell counts it and the screen says "Not shipped". */
  shipment_id: string | null;
  /** Null on a draft nobody has numbered yet - the field stays null, never invented. */
  shipment_number: string | null;
  /** The shipment's container number, null on an allocation with no shipment yet (S4). */
  container_number: string | null;
  /** The site pool this allocation is bound for. */
  warehouse_code: string | null;
  qty: number;
  received: number;
  eta: string | null;
  arrived_at: string | null;
  status: string | null;
}

/** One packing list carrying this product that has not arrived (reference only, never netted). */
export interface ContainerRequestDrillIncomingPlRow {
  shipment_id: string;
  shipment_number: string | null;
  container_number: string | null;
  supplier_name: string | null;
  qty: number;
  eta: string | null;
  status: string | null;
}

/** One purchase-order LINE: open (what the cell counts) or done (the History tab). */
export interface ContainerRequestDrillPoRow {
  purchase_order_id: string;
  po_number: string | null;
  supplier_name: string | null;
  qty_ordered: number;
  still_to_come: number;
  unit_price: number | null;
  currency: string | null;
  issued: string | null;
  eta: string | null;
  status: string | null;
}

export type ContainerRequestDrillRow =
  | ContainerRequestDrillSpoRow
  | ContainerRequestDrillIncomingPlRow
  | ContainerRequestDrillPoRow;

export interface ContainerRequestDrill<TRow = ContainerRequestDrillRow> {
  kind: ContainerRequestDrillKind;
  rows: TRow[];
  /** The figure the cell shows, summed over `rows` by the backend. */
  total: number;
  /** Empty for `incoming_pl`: an arrived packing list IS the On hand dialog. */
  history: TRow[];
}

/** GET /api/v1/scm/container-requests/drill?supplier_id&product_id&kind */
export async function getContainerRequestDrill(
  supplierId: string,
  productId: string,
  kind: ContainerRequestDrillKind,
): Promise<ContainerRequestDrill> {
  const params = new URLSearchParams({
    supplier_id: supplierId,
    product_id: productId,
    kind,
  });
  const res = await apiFetch(`/api/v1/scm/container-requests/drill?${params.toString()}`);
  if (!res.ok) {
    throw new Error(await extractApiError(res, 'Failed to load the documents behind this figure'));
  }
  return res.json();
}
