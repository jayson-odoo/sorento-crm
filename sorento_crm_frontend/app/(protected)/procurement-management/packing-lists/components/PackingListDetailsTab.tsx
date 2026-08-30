'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { formatDate } from '@/lib/helpers';
import { CLEARANCE_ATTRIBUTE_FIELDS } from '../forms/packing-list-schema';
import { PackingListField } from './PackingListField';
import { SupplierCombobox } from './SupplierCombobox';
import {
  CONTAINER_COST_FIELDS,
  usePackingListRecord,
} from '../[id]/components/packing-list-context';

/** The header field this checkpoint is already edited in, so it is not asked for twice. */
const CHECKPOINTS_RENDERED_ELSEWHERE = new Set(['estimated_arrival_date']);

/**
 * Everything about the container itself: what it is, when it moves, what it costs to land.
 *
 * View and edit are the SAME layout throughout - the same fields in the same order, and an
 * input where the value was. Every card and every row is rendered whether it has a value or
 * not: per the CRUD standard a section is never hidden on missing data, and "-" is the
 * honest answer for a container that has not cleared yet.
 */
export function PackingListDetailsTab() {
  const {
    packingList,
    editing,
    draft,
    setField,
    suppliers,
    lineSupplierNames,
    checkpoints,
  } = usePackingListRecord();

  if (!packingList) return null;
  const record = packingList as unknown as Record<string, unknown>;

  // Total items from the lines when there are any (the source of truth), else the header's
  // own figure. Derived by the backend, so it has no input counterpart.
  const totalItemsFromLines =
    packingList.shipment_lines?.reduce(
      (sum, line) => sum + (line.quantity_shipped ?? 0),
      0,
    ) ?? 0;
  const displayTotalItems =
    packingList.shipment_lines?.length && totalItemsFromLines > 0
      ? totalItemsFromLines
      : packingList.total_items_shipped ?? 0;

  const text = (value: unknown) =>
    value === null || value === undefined || value === '' ? '-' : String(value);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Shipment Information</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <PackingListField
              label="Shipment Number"
              name="shipment_number"
              editing={editing}
              draft={draft}
              onChange={setField}
              view={packingList.shipment_number || '-'}
            />
            <div>
              <p className="text-sm text-muted-foreground">Supplier</p>
              {editing ? (
                <SupplierCombobox
                  className="mt-1"
                  value={draft.supplier_id ?? ''}
                  onChange={(v) => setField('supplier_id', v)}
                  suppliers={suppliers}
                  supplierFallback={packingList.supplier ?? null}
                  placeholder="No supplier on the header"
                />
              ) : (
                <p className="font-medium">
                  {packingList.supplier?.supplier_name || lineSupplierNames || '-'}
                </p>
              )}
            </div>
            <PackingListField
              label="Shipment Date"
              name="shipment_date"
              type="date"
              editing={editing}
              draft={draft}
              onChange={setField}
              view={
                packingList.shipment_date
                  ? formatDate(new Date(packingList.shipment_date))
                  : '-'
              }
            />
            <PackingListField
              label="Estimated Arrival Date"
              name="estimated_arrival_date"
              type="date"
              editing={editing}
              draft={draft}
              onChange={setField}
              view={
                packingList.estimated_arrival_date
                  ? formatDate(new Date(packingList.estimated_arrival_date))
                  : '-'
              }
            />
            <PackingListField
              label="Actual Arrival Date"
              name="actual_arrival_date"
              type="date"
              editing={editing}
              draft={draft}
              onChange={setField}
              view={
                packingList.actual_arrival_date
                  ? formatDate(new Date(packingList.actual_arrival_date))
                  : '-'
              }
            />
            <PackingListField
              label="Bill of Lading Number"
              name="bill_of_lading_number"
              editing={editing}
              draft={draft}
              onChange={setField}
              view={packingList.bill_of_lading_number || '-'}
            />
            <PackingListField
              label="Shipping Container Number"
              name="shipping_container_number"
              editing={editing}
              draft={draft}
              onChange={setField}
              view={packingList.shipping_container_number || '-'}
            />
            {/* The three the container workbook prints in its header block and nothing
                else on this page ever asked for. */}
            <PackingListField
              label="Seal No"
              name="seal_number"
              editing={editing}
              draft={draft}
              onChange={setField}
              view={packingList.seal_number || '-'}
            />
            <PackingListField
              label="Shipper"
              name="shipper"
              editing={editing}
              draft={draft}
              onChange={setField}
              view={packingList.shipper || '-'}
            />
            <PackingListField
              label="Forwarder order ref"
              name="forwarder_order_ref"
              editing={editing}
              draft={draft}
              onChange={setField}
              view={packingList.forwarder_order_ref || '-'}
            />
            <PackingListField
              label="Invoice Number"
              name="invoice_number"
              editing={editing}
              draft={draft}
              onChange={setField}
              view={packingList.invoice_number || '-'}
            />
            <div>
              {/* Derived from the lines by the backend, so it has no input counterpart -
                  typing our own here would let the two disagree. */}
              <p className="text-sm text-muted-foreground">Total Items</p>
              <p className="font-medium">{displayTotalItems}</p>
            </div>
          </div>
          {/* Always rendered, not only when it has a value: a field that appears solely in
              edit mode is a field nobody knows exists. */}
          <div>
            <p className="text-sm text-muted-foreground">Notes</p>
            {editing ? (
              <Textarea
                className="mt-1"
                rows={3}
                value={draft.notes ?? ''}
                onChange={(e) => setField('notes', e.target.value)}
                aria-label="Notes"
              />
            ) : (
              <p className="font-medium">{packingList.notes || '-'}</p>
            )}
          </div>
        </CardContent>
      </Card>

      {/* What it costs to land this container. Typed per container, never per line: the
          workbook apportions each figure between SORENTO and MOCHA by that company's share
          of the volume (clearance, freight) or of the amount (insurance). */}
      <Card>
        <CardHeader>
          <CardTitle>Container costs</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {CONTAINER_COST_FIELDS.map((f) => (
              <PackingListField
                key={f.name}
                label={f.label}
                name={f.name}
                type="number"
                step="0.0001"
                editing={editing}
                draft={draft}
                onChange={setField}
                view={text(record[f.name])}
              />
            ))}
          </div>
        </CardContent>
      </Card>

      {/* The clearance record. The workbook import normally fills these; before the first
          import - or when a liner revises an ETA between imports - somebody types one, and
          the ADR asks for the record to be edited where it is read. */}
      <Card>
        <CardHeader>
          <CardTitle>Clearance Details</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {checkpoints
              .filter((cp) => !CHECKPOINTS_RENDERED_ELSEWHERE.has(cp.field))
              .map((cp) => {
                const value = record[cp.field];
                return (
                  <PackingListField
                    key={cp.field}
                    label={cp.label}
                    name={cp.field}
                    type="date"
                    editing={editing}
                    draft={draft}
                    onChange={setField}
                    view={value ? formatDate(new Date(String(value))) : '-'}
                  />
                );
              })}
            {CLEARANCE_ATTRIBUTE_FIELDS.map((f) => (
              <PackingListField
                key={f.name}
                label={f.label}
                name={f.name}
                editing={editing}
                draft={draft}
                onChange={setField}
                view={text(record[f.name])}
              />
            ))}
            <div className="min-w-0">
              {/* Provenance, not an editable attribute - it says which workbook tab the
                  row came from, so it is shown but never typed. */}
              <p className="text-sm text-muted-foreground">Source sheet</p>
              <p className="font-medium break-words">{packingList.source_sheet || '-'}</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default PackingListDetailsTab;
