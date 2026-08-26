'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { toast } from 'sonner';
import { GitBranch } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardHeading, CardTitle, CardToolbar } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import {
  useMarkProformaInvoiceAsRevision,
  useProformaInvoices,
} from '../../../hooks/useProformaInvoices';
import { EM_DASH, fmtDate, fmtQty, fmtSupplierCost } from '../../../lib/format';
import type { ProformaInvoiceDetail } from '../../../services/proformaInvoiceService';

/**
 * The revision chain, and what the supplier changed in it (AC-E7, AC-E8, AC-E11).
 *
 * Always rendered, with an explicit empty state, per the CRUD standard: "this is the only
 * version they have sent" is a fact worth reading, and a section that appears only sometimes
 * is a section nobody learns where to find.
 *
 * The diff compares the two documents AS THE SUPPLIER SENT THEM - their frozen quantity and
 * price on both sides - so a line Sorento trimmed to fit the container is not reported as
 * something the supplier changed.
 */
export function ProformaRevisionsCard({
  invoice,
  canEdit,
}: {
  invoice: ProformaInvoiceDetail;
  canEdit: boolean;
}) {
  const [linkOpen, setLinkOpen] = useState(false);
  const [previousId, setPreviousId] = useState<string | null>(null);
  const markAsRevision = useMarkProformaInvoiceAsRevision(invoice.id);
  // The supplier's other invoices, so "which document does this revise" is a pick, never a
  // typed identifier. Loaded only while the dialog is open.
  const siblings = useProformaInvoices(linkOpen ? invoice.supplier_id : null, { limit: 100 });

  const options = useMemo(
    () =>
      (siblings.data?.data ?? [])
        .filter((row) => row.id !== invoice.id && row.status !== 'superseded')
        .map((row) => ({
          value: row.id,
          label: `${row.pi_number} - ${fmtDate(row.invoice_date)}`,
        })),
    [siblings.data, invoice.id],
  );

  const diff = invoice.diff;
  const chain = invoice.revisions ?? [];

  const runLink = async () => {
    if (!previousId) return;
    try {
      await markAsRevision.mutateAsync(previousId);
      setLinkOpen(false);
      setPreviousId(null);
      toast.success('Linked to the document it revises.');
    } catch {
      // The hook toasts the refusal; the dialog stays open on the choice that was refused.
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardHeading>
          <CardTitle>Revisions</CardTitle>
        </CardHeading>
        <CardToolbar>
          {canEdit && !invoice.revision_of_pi_number ? (
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => setLinkOpen(true)}
            >
              <GitBranch className="size-4" />
              Mark as revision of
            </Button>
          ) : null}
        </CardToolbar>
      </CardHeader>

      <div className="space-y-3 p-4 pt-0">
        {chain.length < 2 ? (
          <p className="text-sm text-muted-foreground">
            This is the only version the supplier has sent.
          </p>
        ) : (
          <>
            <p className="text-sm font-medium">
              Revision {invoice.revision_no} of {invoice.revision_count}
            </p>
            <ul className="divide-y divide-border rounded-lg border">
              {chain.map((rev) => (
                <li
                  key={rev.id}
                  className="flex flex-col gap-1 p-2.5 sm:flex-row sm:items-center sm:justify-between"
                >
                  <span className="flex min-w-0 flex-wrap items-center gap-2">
                    {rev.id === invoice.id ? (
                      <span className="truncate text-sm font-medium">{rev.pi_number}</span>
                    ) : (
                      <Link
                        href={`/scm/proforma-invoices/${rev.id}`}
                        className="truncate text-sm font-medium text-primary hover:underline"
                      >
                        {rev.pi_number}
                      </Link>
                    )}
                    <Badge
                      variant={rev.status === 'superseded' ? 'secondary' : 'success'}
                      appearance="light"
                    >
                      Revision {rev.revision_no}
                      {rev.status === 'superseded' ? ' - superseded' : ''}
                    </Badge>
                  </span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {fmtDate(rev.invoice_date)} - {rev.line_count} lines -{' '}
                    {fmtSupplierCost(rev.total_amount, invoice.currency)}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}

        {diff ? (
          <div className="space-y-2">
            <p className="text-sm font-medium">
              {diff.price_changed_lines > 0
                ? `Price changed on ${diff.price_changed_lines} ${diff.price_changed_lines === 1 ? 'line' : 'lines'}`
                : 'No price changed'}
              <span className="ms-1 font-normal text-muted-foreground">
                against {diff.compared_to_pi_number}
                {diff.qty_changed_lines > 0
                  ? `, quantity on ${diff.qty_changed_lines}`
                  : ''}
                {diff.added_lines > 0 ? `, ${diff.added_lines} added` : ''}
                {diff.removed_lines > 0 ? `, ${diff.removed_lines} removed` : ''}
              </span>
            </p>
            {diff.changes.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                The supplier sent the same figures again.
              </p>
            ) : (
              <ul className="divide-y divide-border rounded-lg border text-xs">
                {diff.changes.map((change) => (
                  <li
                    key={`${change.item_code}-${change.occurrence}-${change.status}`}
                    className="flex flex-col gap-1 p-2.5 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <span className="truncate font-medium" title={change.item_code}>
                        {change.item_code}
                      </span>
                      {change.status !== 'changed' ? (
                        <Badge variant="secondary" appearance="light">
                          {change.status === 'added' ? 'Added' : 'Removed'}
                        </Badge>
                      ) : null}
                    </span>
                    <span className="flex shrink-0 flex-wrap gap-3 tabular-nums">
                      {change.unit_price_changed ? (
                        <span>
                          Price{' '}
                          <span className="text-muted-foreground line-through">
                            {change.unit_price_was == null
                              ? EM_DASH
                              : fmtSupplierCost(change.unit_price_was, invoice.currency)}
                          </span>{' '}
                          <span className="font-medium">
                            {change.unit_price_now == null
                              ? EM_DASH
                              : fmtSupplierCost(change.unit_price_now, invoice.currency)}
                          </span>
                        </span>
                      ) : null}
                      {change.qty_changed ? (
                        <span>
                          Qty{' '}
                          <span className="text-muted-foreground line-through">
                            {change.qty_was == null ? EM_DASH : fmtQty(change.qty_was)}
                          </span>{' '}
                          <span className="font-medium">
                            {change.qty_now == null ? EM_DASH : fmtQty(change.qty_now)}
                          </span>
                        </span>
                      ) : null}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : null}
      </div>

      <AlertDialog open={linkOpen} onOpenChange={setLinkOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Mark as a revision</AlertDialogTitle>
            <AlertDialogDescription>
              {invoice.pi_number} becomes the current version, and the document it revises is
              superseded and read-only.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="pi-previous-revision" className="text-xs">
              This is a revision of
            </Label>
            <SearchableSelect
              id="pi-previous-revision"
              value={previousId ?? ''}
              onChange={(v: string) => setPreviousId(v || null)}
              options={options}
              placeholder="Choose the earlier document"
              emptyMessage="No other proforma invoice on file for this supplier."
              clearable
            />
          </div>
          <AlertDialogFooter>
            <Button variant="outline" onClick={() => setLinkOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => void runLink()}
              disabled={!previousId || markAsRevision.isPending}
            >
              Link
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}

export default ProformaRevisionsCard;
