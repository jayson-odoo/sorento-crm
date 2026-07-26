'use client';

import * as React from 'react';
import { AlertTriangle, Pencil, Plus, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import {
  usePurchaseOrderLineMutations,
  usePurchaseOrderLines,
} from '../../_shared/hooks/useProjects';
import type {
  Project,
  ProjectPurchaseOrder,
  PurchaseOrderLine,
} from '../../_shared/types/project.types';
import { formatMyr } from './QuotationsPanel';
import { PurchaseOrderLineDialog } from './PurchaseOrderLineDialog';

/**
 * The lines of one PO, with what each one was quoted at beside what was ordered.
 *
 * Showing both numbers on the same row is the point: "price differs" on its own sends
 * the user hunting through the quotation, and the difference is usually the thing they
 * want to talk to the contractor about within the next ten minutes.
 */
export function PurchaseOrderLinesEditor({
  project,
  po,
}: {
  project: Project;
  po: ProjectPurchaseOrder;
}) {
  const lines = usePurchaseOrderLines(po.id);
  const { remove } = usePurchaseOrderLineMutations(project.id, po.id);

  const [adding, setAdding] = React.useState(false);
  const [editing, setEditing] = React.useState<PurchaseOrderLine | null>(null);
  const [deleting, setDeleting] = React.useState<PurchaseOrderLine | null>(null);

  const rows = React.useMemo(
    () => [...(lines.data ?? [])].sort((a, b) => a.sort_order - b.sort_order),
    [lines.data],
  );
  const nextSortOrder =
    rows.length === 0 ? 0 : Math.max(...rows.map((line) => line.sort_order)) + 10;
  const editable = project.can_edit;

  if (lines.isLoading) return <Skeleton className="h-20 w-full" />;

  return (
    <div className="space-y-3">
      {!po.quotation_version_id && (
        <p className="rounded-md bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
          This PO is not tied to a quotation version, so nothing here is compared against
          a quoted price. Bind it to a version to get the checks.
        </p>
      )}

      {rows.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border px-6 py-8 text-center">
          <h4 className="text-sm font-semibold">No lines entered</h4>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            {editable
              ? 'Enter what the PO ordered and each line is checked against the quoted version.'
              : 'This PO was recorded as a single amount with no line detail.'}
          </p>
          {editable && (
            <Button type="button" size="sm" className="mt-3" onClick={() => setAdding(true)}>
              <Plus className="size-4" aria-hidden />
              Add the first line
            </Button>
          )}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-xs text-muted-foreground">
                <th className="py-1.5 pe-3 text-start font-medium">Item</th>
                <th className="py-1.5 pe-3 text-end font-medium">Qty</th>
                <th className="py-1.5 pe-3 text-end font-medium">Ordered at</th>
                <th className="py-1.5 pe-3 text-end font-medium">Total</th>
                {editable && <th className="py-1.5 w-20" />}
              </tr>
            </thead>
            <tbody>
              {rows.map((line) => (
                <tr key={line.id} className="border-b border-border/60 align-top">
                  <td className="py-2 pe-3">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-medium">
                        {line.product_code ?? 'Unnamed item'}
                      </span>
                      {line.model_mismatch && (
                        <Badge
                          variant="destructive"
                          className="gap-1 text-[11px]"
                          title="This item does not appear on the quoted version"
                        >
                          <AlertTriangle className="size-3" aria-hidden />
                          Not quoted
                        </Badge>
                      )}
                      {line.price_mismatch && (
                        <Badge variant="destructive" className="text-[11px]">
                          Price differs
                        </Badge>
                      )}
                    </div>
                    {line.description && (
                      <div
                        className="mt-0.5 max-w-md truncate text-xs text-muted-foreground"
                        title={line.description}
                      >
                        {line.description}
                      </div>
                    )}
                  </td>
                  <td className="py-2 pe-3 text-end whitespace-nowrap">
                    {trimAmount(line.quantity)}
                    {line.uom ? ` ${line.uom}` : ''}
                  </td>
                  <td className="py-2 pe-3 text-end whitespace-nowrap">
                    {formatMyr(line.unit_price)}
                    {line.quoted_unit_price && (
                      <span
                        className={
                          line.price_mismatch
                            ? 'block text-xs text-destructive'
                            : 'block text-xs text-muted-foreground'
                        }
                      >
                        {`Quoted ${formatMyr(line.quoted_unit_price)}`}
                      </span>
                    )}
                  </td>
                  <td className="py-2 pe-3 text-end font-medium whitespace-nowrap">
                    {formatMyr(line.line_total)}
                  </td>
                  {editable && (
                    <td className="py-2">
                      <div className="flex items-center justify-end gap-0.5">
                        <Button
                          mode="icon"
                          variant="ghost"
                          size="sm"
                          onClick={() => setEditing(line)}
                          aria-label={`Edit ${line.product_code ?? 'line'}`}
                        >
                          <Pencil className="size-3.5" />
                        </Button>
                        <Button
                          mode="icon"
                          variant="ghost"
                          size="sm"
                          onClick={() => setDeleting(line)}
                          aria-label={`Remove ${line.product_code ?? 'line'}`}
                        >
                          <Trash2 className="size-3.5 text-destructive" />
                        </Button>
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editable && rows.length > 0 && (
        <Button type="button" size="sm" variant="outline" onClick={() => setAdding(true)}>
          <Plus className="size-4" aria-hidden />
          Add line
        </Button>
      )}

      {(adding || editing) && (
        <PurchaseOrderLineDialog
          projectId={project.id}
          po={po}
          line={editing}
          nextSortOrder={nextSortOrder}
          onDone={() => {
            setAdding(false);
            setEditing(null);
          }}
        />
      )}

      <ConfirmDeleteDialog
        open={Boolean(deleting)}
        onOpenChange={(next) => !next && setDeleting(null)}
        title="Confirm delete"
        description={
          deleting
            ? `Remove "${deleting.product_code ?? deleting.description ?? 'this line'}" from ${po.po_number}? This action cannot be undone.`
            : ''
        }
        onDelete={async () => {
          if (!deleting) return;
          await remove.mutateAsync(deleting.id);
        }}
        onSuccess={() => setDeleting(null)}
        successMessage="Line removed"
      />
    </div>
  );
}

function trimAmount(value: string): string {
  const amount = Number(value);
  if (Number.isNaN(amount)) return value;
  return String(amount);
}
