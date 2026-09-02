'use client';

import * as React from 'react';
import Link from 'next/link';
import { ExternalLink } from 'lucide-react';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateInMalaysia } from '@/lib/helpers';
import { statusPillClass } from '@/lib/status-pill';
import {
  useOrderInquiryPoDetail,
  useOrderInquirySpoDetail,
} from '../../_shared/hooks/useOrderInquiry';
import { formatInquiryQty } from '../../_shared/lib/orderInquiryWorklist';
import type { OrderInquiryDocumentAllocation } from '../../_shared/types/orderInquiry.types';

/**
 * ONE document, read-only, in a real dialog (R9; the captain, 27 Aug: "the popup on the
 * PO number is bad UI").
 *
 * It replaced a `Popover`, which the grid's own scroll container clipped, could only ever
 * open a purchase order, and left an SPO number as dead text. A dialog carries both
 * books, scrolls inside itself, closes on Escape and fits 375.
 *
 * Read-only with exactly one way out: "Open document". A lightbox that offered actions
 * would be a second place to act on a document, and this page's actions are all bulk.
 */
export function OrderInquiryDocumentDialog({
  kind,
  document,
  poId,
  open,
  onOpenChange,
}: {
  kind: 'po' | 'spo';
  /** `202607-S0105` or `SPO-2026/08-0015`. Never an id: it is what the buyer quotes. */
  document: string;
  /** Addresses the purchase order. Null on an SPO, which is addressed by its number. */
  poId?: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl" data-testid={`document-detail-${document}`}>
        <DialogHeader>
          <DialogTitle className="tabular-nums">{document}</DialogTitle>
          <DialogDescription>
            {kind === 'po' ? 'Purchase order' : 'Shipping order'}
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="max-h-[70vh] overflow-y-auto">
          {kind === 'po' ? (
            <PoBody poId={poId ?? null} open={open} />
          ) : (
            <SpoBody spoNumber={document} open={open} />
          )}
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}

/**
 * The document number as it sits in the grid: a button that opens the lightbox, for
 * BOTH kinds. The dialog is mounted only once it has been asked for, so a page of forty
 * rows does not carry forty dialogs.
 */
export function OrderInquiryDocumentLink({
  kind,
  document,
  poId,
}: {
  kind: 'po' | 'spo';
  document: string;
  poId?: string | null;
}) {
  const [open, setOpen] = React.useState(false);
  return (
    <>
      <button
        type="button"
        data-testid={`document-detail-trigger-${document}`}
        className="block max-w-full truncate rounded-sm font-medium tabular-nums text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        title={document}
        onClick={(event) => {
          event.stopPropagation();
          setOpen(true);
        }}
      >
        {document}
      </button>
      {open ? (
        <OrderInquiryDocumentDialog
          kind={kind}
          document={document}
          poId={poId}
          open
          onOpenChange={setOpen}
        />
      ) : null}
    </>
  );
}

function LoadingBody() {
  return (
    <div className="space-y-2">
      <Skeleton className="h-4 w-2/3" />
      <Skeleton className="h-4 w-1/2" />
      <Skeleton className="h-24 w-full" />
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-2xs text-muted-foreground">{label}</dt>
      <dd className="truncate text-sm font-medium">{children}</dd>
    </div>
  );
}

function NotStated() {
  return <span className="font-normal text-muted-foreground">Not stated</span>;
}

/**
 * Who this document's quantity is spoken for by (plan section 4.3). No Standing column
 * any more (nit, review of PR #471): a row is born acknowledged (S1), so every allocation
 * reads Confirmed and the column said nothing a person could act on.
 */
function AllocationsPanel({
  allocations,
}: {
  allocations?: OrderInquiryDocumentAllocation[] | null;
}) {
  return (
    <section className="space-y-2">
      <h3 className="text-sm font-semibold">Allocated to</h3>
      {!allocations || allocations.length === 0 ? (
        <p className="text-xs text-muted-foreground">No allocations yet.</p>
      ) : (
        <div className="overflow-x-auto overscroll-x-contain rounded-md border">
          <table className="w-full min-w-[480px] text-xs tabular-nums">
            <thead>
              <tr className="border-b text-muted-foreground">
                <th className="px-3 py-1.5 text-start font-medium uppercase tracking-wide">
                  Order inquiry
                </th>
                <th className="px-3 py-1.5 text-start font-medium uppercase tracking-wide">
                  S/O no
                </th>
                <th className="px-3 py-1.5 text-start font-medium uppercase tracking-wide">
                  Item
                </th>
                <th className="px-2 py-1.5 text-end font-medium uppercase tracking-wide">
                  Qty
                </th>
              </tr>
            </thead>
            <tbody>
              {allocations.map((allocation, index) => (
                <tr
                  key={`${allocation.inquiry_no ?? 'allocation'}-${allocation.item_code ?? ''}-${index}`}
                  className="border-b last:border-b-0"
                >
                  <td className="px-3 py-1.5">
                    {allocation.inquiry_no || (
                      <span className="text-muted-foreground">Not numbered</span>
                    )}
                  </td>
                  <td className="px-3 py-1.5">
                    {allocation.so_number || (
                      <span className="text-muted-foreground">Not numbered</span>
                    )}
                  </td>
                  <td className="max-w-[180px] px-3 py-1.5">
                    <span className="block truncate" title={allocation.item_code ?? ''}>
                      {allocation.item_code || (
                        <span className="text-muted-foreground">Unresolved</span>
                      )}
                    </span>
                  </td>
                  <td className="px-2 py-1.5 text-end font-medium">
                    {formatInquiryQty(allocation.qty)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function LinesTable({
  headers,
  children,
  empty,
  isEmpty,
}: {
  headers: { label: string; align?: 'start' | 'end' }[];
  children: React.ReactNode;
  empty: string;
  isEmpty: boolean;
}) {
  if (isEmpty) return <p className="text-xs text-muted-foreground">{empty}</p>;
  return (
    <div className="overflow-x-auto overscroll-x-contain rounded-md border">
      <table className="w-full min-w-[520px] text-xs tabular-nums">
        <thead>
          <tr className="border-b text-muted-foreground">
            {headers.map((header) => (
              <th
                key={header.label}
                className={`px-3 py-1.5 font-medium uppercase tracking-wide ${
                  header.align === 'end' ? 'text-end' : 'text-start'
                }`}
              >
                {header.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

function SkuCell({ sku, name }: { sku?: string | null; name?: string | null }) {
  return (
    <td className="max-w-[220px] px-3 py-1.5">
      <div className="min-w-0">
        <span className="block truncate font-medium" title={sku ?? ''}>
          {sku || <span className="text-muted-foreground">Unresolved</span>}
        </span>
        {name && name !== sku ? (
          <span className="block truncate text-muted-foreground" title={name}>
            {name}
          </span>
        ) : null}
      </div>
    </td>
  );
}

function LocationCell({ location }: { location?: string | null }) {
  return (
    <td className="px-3 py-1.5">
      {location || <span className="text-muted-foreground">no location</span>}
    </td>
  );
}

function PoBody({ poId, open }: { poId: string | null; open: boolean }) {
  const { data, isLoading, isError, error } = useOrderInquiryPoDetail(poId ?? undefined, {
    enabled: open && Boolean(poId),
  });

  if (!poId) {
    return (
      <p className="text-sm text-muted-foreground">
        This link does not reach a purchase order in the system.
      </p>
    );
  }
  if (isLoading) return <LoadingBody />;
  if (isError || !data) {
    return (
      <p className="text-sm text-destructive">
        {error instanceof Error ? error.message : 'Could not load this purchase order.'}
      </p>
    );
  }

  // The NAME, not the code: the code is one unbroken token that truncates into nothing a
  // person can read. The code rides on the title.
  const supplier = data.supplier_name || data.supplier_code || null;
  const supplierTitle =
    [data.supplier_name, data.supplier_code].filter(Boolean).join(' - ') || undefined;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <dl className="grid min-w-0 flex-1 grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-3">
          <Field label="Supplier">
            <span title={supplierTitle}>{supplier ?? <NotStated />}</span>
          </Field>
          <Field label="Status">
            <span
              className={`inline-flex items-center rounded px-1.5 py-0.5 text-2xs font-medium capitalize ${statusPillClass(data.status)}`}
            >
              {data.status}
            </span>
          </Field>
          <Field label="Expected">
            {data.expected_date ? formatDateInMalaysia(data.expected_date) : <NotStated />}
          </Field>
        </dl>
        <Link
          href={`/scm/purchase-orders/${data.id}`}
          className="inline-flex shrink-0 items-center gap-1 text-sm font-medium text-primary hover:underline"
        >
          Open document
          <ExternalLink className="size-3.5" aria-hidden />
        </Link>
      </div>

      <section className="space-y-2">
        <h3 className="text-sm font-semibold">Lines</h3>
        <LinesTable
          isEmpty={data.lines.length === 0}
          empty="This purchase order carries no lines."
          headers={[
            { label: 'SKU' },
            { label: 'Ordered', align: 'end' },
            { label: 'Received', align: 'end' },
            { label: 'Remaining', align: 'end' },
            { label: 'Location' },
          ]}
        >
          {data.lines.map((line, index) => (
            <tr key={`${line.sku ?? 'line'}-${index}`} className="border-b last:border-b-0">
              <SkuCell sku={line.sku} name={line.product_name} />
              <td className="px-3 py-1.5 text-end">{formatInquiryQty(line.qty_ordered)}</td>
              <td className="px-3 py-1.5 text-end">{formatInquiryQty(line.qty_received)}</td>
              <td className="px-3 py-1.5 text-end font-medium">
                {formatInquiryQty(line.remaining)}
              </td>
              <LocationCell location={line.location} />
            </tr>
          ))}
        </LinesTable>
      </section>

      <AllocationsPanel allocations={data.allocations} />
    </div>
  );
}

function SpoBody({ spoNumber, open }: { spoNumber: string; open: boolean }) {
  const { data, isLoading, isError } = useOrderInquirySpoDetail(spoNumber, { enabled: open });

  if (isLoading) return <LoadingBody />;
  if (isError || !data) {
    // A number no allocation carries answers 404, which is the honest reading of a
    // document this system does not hold - a shipping order the book has never named.
    return (
      <p className="text-sm text-muted-foreground">
        This shipping order could not be found.
      </p>
    );
  }

  return (
    <div className="space-y-5">
      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-4">
        <Field label="Supplier">{data.supplier_name || <NotStated />}</Field>
        <Field label="ETA">
          {data.eta ? formatDateInMalaysia(data.eta) : <NotStated />}
        </Field>
        <Field label="Shipment">{data.shipment_ref || <NotStated />}</Field>
        <Field label="Container">{data.container_no || <NotStated />}</Field>
      </dl>

      <section className="space-y-2">
        <h3 className="text-sm font-semibold">Lines</h3>
        <LinesTable
          isEmpty={data.lines.length === 0}
          empty="This shipping order carries no lines."
          headers={[
            { label: 'SKU' },
            { label: 'Allocated', align: 'end' },
            { label: 'Received', align: 'end' },
            { label: 'Remaining', align: 'end' },
            { label: 'Location' },
          ]}
        >
          {data.lines.map((line, index) => (
            <tr key={`${line.sku ?? 'line'}-${index}`} className="border-b last:border-b-0">
              <SkuCell sku={line.sku} name={line.product_name} />
              <td className="px-3 py-1.5 text-end">{formatInquiryQty(line.allocated)}</td>
              <td className="px-3 py-1.5 text-end">{formatInquiryQty(line.received)}</td>
              <td className="px-3 py-1.5 text-end font-medium">
                {formatInquiryQty(line.remaining)}
              </td>
              <LocationCell location={line.location} />
            </tr>
          ))}
        </LinesTable>
      </section>

      <AllocationsPanel allocations={data.allocations} />
    </div>
  );
}

export default OrderInquiryDocumentDialog;
