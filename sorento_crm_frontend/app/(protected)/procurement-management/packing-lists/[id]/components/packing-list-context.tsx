'use client';

import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';
import { toast } from 'sonner';
import {
  usePackingList,
  usePackingListSourceInvoices,
  useClearanceCheckpoints,
  useUpdatePackingList,
} from '../../hooks/usePackingLists';
import { useSupplierSelectQuery } from '../../../suppliers/hooks/useSupplierSelectQuery';
import { CLEARANCE_ATTRIBUTE_FIELDS } from '../../forms/packing-list-schema';
import type {
  PackingListDetail,
  PackingListFormData,
} from '../../types/packingList.types';
import type {
  ClearanceCheckpoint,
  PackingListSourceInvoices,
} from '../../services/packingListService';

/**
 * The record the whole tab set reads, and the ONE edit draft it shares.
 *
 * The tabs are routes now (Details, Proforma invoices, Shipment lines, Documents, SPO
 * planner, Timeline), and Edit lives on the layout's toolbar above all of them - so the
 * draft cannot live inside a tab. It is still ONE edit mode for the record and ONE `PUT`
 * on Save, which is what stops a header saved from one tab and lines saved from another
 * disagreeing about which version of the container is current.
 */

/** One line as it is being edited. `id` is absent on a line the operator just added. */
export interface DraftLine {
  key: string;
  id?: string;
  product_id: string;
  product_code: string;
  product_name: string | null;
  quantity_shipped: string;
  supplier_id: string;
  cartons_count: string;
  cbm: string;
  material: string;
  pcs_per_carton: string;
  carton_length_cm: string;
  carton_width_cm: string;
  carton_height_cm: string;
  net_weight_per_carton: string;
  gross_weight_per_carton: string;
  uom_id: string | null;
  /** Round-tripped untouched: the PUT dropped it, so the price lost its unit on every save. */
  currency: string | null;
}

/** The header fields the Details tab types, beyond the clearance ones. */
export const CONTAINER_COST_FIELDS = [
  { name: 'clearance_cost', label: 'Clearance cost' },
  { name: 'china_freight_cost', label: 'China freight cost' },
  { name: 'insurance_rate', label: 'Insurance rate' },
] as const;

interface PackingListContextValue {
  packingListId: string;
  packingList: PackingListDetail | undefined;
  isLoading: boolean;
  suppliers: Array<{ id: string; supplier_code: string; supplier_name: string }>;
  supplierNameById: Map<string, string>;
  /** Every factory named on the lines, in the order they appear. */
  lineSupplierNames: string;
  checkpoints: ClearanceCheckpoint[];
  sourceInvoices: PackingListSourceInvoices | undefined;
  editing: boolean;
  saving: boolean;
  draft: Record<string, string>;
  draftLines: DraftLine[];
  setField: (name: string, value: string) => void;
  setLineField: (key: string, name: keyof DraftLine, value: string) => void;
  addLine: () => void;
  removeLine: (key: string) => void;
  beginEdit: () => void;
  cancelEdit: () => void;
  saveEdit: () => Promise<void>;
  /** For the Documents tab, which links and unlinks an attachment on its own. */
  update: (data: Partial<PackingListFormData>) => Promise<unknown>;
  updatePending: boolean;
}

const PackingListContext = createContext<PackingListContextValue | null>(null);

export function usePackingListRecord(): PackingListContextValue {
  const value = useContext(PackingListContext);
  if (!value) {
    throw new Error('usePackingListRecord must be used inside PackingListProvider');
  }
  return value;
}

/** ISO datetime -> `yyyy-mm-dd`, which is what `<input type="date">` speaks. */
export function toDateInput(value: unknown): string {
  if (value === null || value === undefined) return '';
  const s = String(value);
  return /^\d{4}-\d{2}-\d{2}T/.test(s) ? s.slice(0, 10) : s;
}

/** A value as an input holds it: never `undefined`, never `null`, never `"null"`. */
function toInput(value: unknown): string {
  return value === null || value === undefined ? '' : String(value);
}

export function PackingListProvider({
  packingListId,
  children,
}: {
  packingListId: string;
  children: ReactNode;
}) {
  const { data: packingList, isLoading } = usePackingList(packingListId);
  const { data: suppliers = [] } = useSupplierSelectQuery();
  const { data: checkpoints = [] } = useClearanceCheckpoints();
  // The proforma invoices behind this container, read ONCE for the four places that show
  // them: the Proforma invoices tab, the Lines column, the Timeline entry and Documents.
  const { data: sourceInvoices } = usePackingListSourceInvoices(packingListId);
  const updateMutation = useUpdatePackingList();

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [draftLines, setDraftLines] = useState<DraftLine[]>([]);
  const [saving, setSaving] = useState(false);

  const supplierNameById = useMemo(() => {
    const byId = new Map<string, string>();
    for (const s of suppliers) byId.set(s.id, s.supplier_name);
    // The header's own supplier is already resolved on the payload, so it stays readable
    // even before the select answers.
    if (packingList?.supplier) {
      byId.set(packingList.supplier.id, packingList.supplier.supplier_name);
    }
    return byId;
  }, [suppliers, packingList?.supplier]);

  /**
   * One container is routinely loaded by two or three factories, and the header supplier is
   * null once it is mixed - the lines are then the only record of who loaded it, so a page
   * reading the header alone would say "No supplier" about a full container.
   */
  const lineSupplierNames = useMemo(() => {
    const names: string[] = [];
    for (const line of packingList?.shipment_lines ?? []) {
      if (!line.supplier_id) continue;
      const name = supplierNameById.get(line.supplier_id);
      if (name && !names.includes(name)) names.push(name);
    }
    return names.join(', ');
  }, [packingList?.shipment_lines, supplierNameById]);

  const beginEdit = () => {
    if (!packingList) return;
    // Read from the server's answer every time. A draft left over from a cancelled edit
    // would silently re-apply a value the operator backed out of.
    const record = packingList as unknown as Record<string, unknown>;
    const next: Record<string, string> = {
      shipment_number: packingList.shipment_number ?? '',
      supplier_id: packingList.supplier_id ?? '',
      shipment_date: toDateInput(packingList.shipment_date),
      estimated_arrival_date: toDateInput(packingList.estimated_arrival_date),
      actual_arrival_date: toDateInput(packingList.actual_arrival_date),
      bill_of_lading_number: packingList.bill_of_lading_number ?? '',
      shipping_container_number: packingList.shipping_container_number ?? '',
      invoice_number: packingList.invoice_number ?? '',
      seal_number: packingList.seal_number ?? '',
      shipper: packingList.shipper ?? '',
      forwarder_order_ref: packingList.forwarder_order_ref ?? '',
      notes: packingList.notes ?? '',
    };
    for (const f of CONTAINER_COST_FIELDS) next[f.name] = toInput(record[f.name]);
    for (const cp of checkpoints) next[cp.field] = toDateInput(record[cp.field]);
    for (const f of CLEARANCE_ATTRIBUTE_FIELDS) next[f.name] = toInput(record[f.name]);
    setDraft(next);
    setDraftLines(
      (packingList.shipment_lines ?? []).map((line) => ({
        key: line.id,
        id: line.id,
        product_id: line.product_id,
        product_code: line.product?.product_code ?? '',
        product_name: line.product?.product_name ?? null,
        quantity_shipped: String(line.quantity_shipped ?? 0),
        supplier_id: line.supplier_id ?? '',
        cartons_count: toInput(line.cartons_count),
        cbm: toInput(line.cbm),
        material: toInput(line.material),
        pcs_per_carton: toInput(line.pcs_per_carton),
        carton_length_cm: toInput(line.carton_length_cm),
        carton_width_cm: toInput(line.carton_width_cm),
        carton_height_cm: toInput(line.carton_height_cm),
        net_weight_per_carton: toInput(line.net_weight_per_carton),
        gross_weight_per_carton: toInput(line.gross_weight_per_carton),
        uom_id: line.uom_id ?? null,
        currency: line.currency ?? null,
      })),
    );
    setEditing(true);
  };

  const cancelEdit = () => {
    setEditing(false);
    setDraft({});
    setDraftLines([]);
  };

  const setField = (name: string, value: string) =>
    setDraft((prev) => ({ ...prev, [name]: value }));

  const setLineField = (key: string, name: keyof DraftLine, value: string) =>
    setDraftLines((prev) =>
      prev.map((line) => (line.key === key ? { ...line, [name]: value } : line)),
    );

  const removeLine = (key: string) =>
    setDraftLines((prev) => prev.filter((line) => line.key !== key));

  /** A blank line for the operator to fill. Its product is the first thing it asks for,
   *  because a shipment line with no product is not a line the backend can store. */
  const addLine = () =>
    setDraftLines((prev) => [
      ...prev,
      {
        key: `new-${prev.length}-${Date.now()}`,
        product_id: '',
        product_code: '',
        product_name: null,
        quantity_shipped: '0',
        supplier_id: '',
        cartons_count: '',
        cbm: '',
        material: '',
        pcs_per_carton: '',
        carton_length_cm: '',
        carton_width_cm: '',
        carton_height_cm: '',
        net_weight_per_carton: '',
        gross_weight_per_carton: '',
        uom_id: null,
        currency: null,
      },
    ]);

  const saveEdit = async () => {
    if (!packingList) return;
    const incomplete = draftLines.find((line) => !line.product_id);
    if (incomplete) {
      toast.error('Every line needs a product. Pick one, or remove the line.');
      return;
    }
    setSaving(true);
    // Only what the operator can actually type. `total_items_shipped` is derived from the
    // lines by the backend, and sending our own would let the two disagree.
    // NULL for a cleared field, never `undefined`: JSON.stringify drops undefined, and the
    // backend PUT is `exclude_unset`, so an omitted key means "unchanged" - the value the
    // operator just deleted came straight back on the next read, reading as a save that did
    // not work.
    const orNull = (value: string | undefined) => (value ?? '').trim() || null;
    // Never the JS literal NaN: `JSON.stringify(NaN)` silently becomes the JSON `null`, and a
    // field the backend declares as a plain (non-Optional) number then 422s on it - the
    // operator sees "[object Object]" for a blank they never even touched. Anything that does
    // not parse is treated the same as blank: nothing was stated.
    const orUndefined = (value: string) => {
      const trimmed = (value ?? '').trim();
      if (trimmed === '') return undefined;
      const n = Number(trimmed);
      return Number.isNaN(n) ? undefined : n;
    };
    const payload: Partial<PackingListFormData> = {
      shipment_number: orNull(draft.shipment_number),
      supplier_id: orNull(draft.supplier_id),
      // Optional on the update schema, so a cleared date is a cleared date - sending the raw
      // (possibly empty) string 422'd instead of clearing anything.
      shipment_date: orNull(draft.shipment_date),
      estimated_arrival_date: orNull(draft.estimated_arrival_date),
      actual_arrival_date: orNull(draft.actual_arrival_date),
      bill_of_lading_number: orNull(draft.bill_of_lading_number),
      shipping_container_number: orNull(draft.shipping_container_number),
      invoice_number: orNull(draft.invoice_number),
      seal_number: orNull(draft.seal_number),
      shipper: orNull(draft.shipper),
      forwarder_order_ref: orNull(draft.forwarder_order_ref),
      notes: orNull(draft.notes),
      shipment_lines: draftLines.map((line) => ({
        product_id: line.product_id,
        // Required and non-nullable on the line schema, so garbage text falls back to 0
        // rather than sending NaN-turned-null and 422ing on a line the operator never meant
        // to touch.
        quantity_shipped: orUndefined(line.quantity_shipped) ?? 0,
        supplier_id: line.supplier_id || undefined,
        uom_id: line.uom_id || undefined,
        // The unit the price is in. Sent back untouched - a payload that carried the cost
        // and dropped this handed the backend a number with no meaning.
        currency: line.currency || undefined,
        cartons_count: orUndefined(line.cartons_count),
        cbm: orUndefined(line.cbm),
        material: line.material.trim() || undefined,
        pcs_per_carton: orUndefined(line.pcs_per_carton),
        carton_length_cm: orUndefined(line.carton_length_cm),
        carton_width_cm: orUndefined(line.carton_width_cm),
        carton_height_cm: orUndefined(line.carton_height_cm),
        net_weight_per_carton: orUndefined(line.net_weight_per_carton),
        gross_weight_per_carton: orUndefined(line.gross_weight_per_carton),
      })),
    };
    // The clearance and cost fields are on the payload schema but not on
    // `PackingListFormData`'s named members, so they go through one cast here rather than
    // the whole payload losing its type.
    const extra = payload as unknown as Record<string, unknown>;
    for (const cp of checkpoints) extra[cp.field] = orNull(draft[cp.field]);
    for (const f of CLEARANCE_ATTRIBUTE_FIELDS) extra[f.name] = orNull(draft[f.name]);
    // A cost cleared back to blank is null, not 0: nobody has priced this container yet
    // and a zero would be apportioned across the companies as a real figure. Unparseable
    // text is treated the same as blank, not sent as NaN-turned-null-turned-422.
    for (const f of CONTAINER_COST_FIELDS) {
      extra[f.name] = orUndefined(draft[f.name] ?? '') ?? null;
    }
    try {
      await updateMutation.mutateAsync({ id: packingListId, data: payload });
      cancelEdit();
    } catch {
      // The mutation hook toasts the message; the edit stays open on the values that were
      // refused rather than throwing every other change away with them.
    } finally {
      setSaving(false);
    }
  };

  const value: PackingListContextValue = {
    packingListId,
    packingList,
    isLoading,
    suppliers,
    supplierNameById,
    lineSupplierNames,
    checkpoints,
    sourceInvoices,
    editing,
    saving,
    draft,
    draftLines,
    setField,
    setLineField,
    addLine,
    removeLine,
    beginEdit,
    cancelEdit,
    saveEdit,
    update: (data: Partial<PackingListFormData>) =>
      updateMutation.mutateAsync({ id: packingListId, data }),
    updatePending: updateMutation.isPending,
  };

  return (
    <PackingListContext.Provider value={value}>{children}</PackingListContext.Provider>
  );
}
