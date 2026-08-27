'use client';

import { useMemo, useState } from 'react';
import { toast } from 'sonner';
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import {
  useMarkProformaInvoiceAsRevision,
  useProformaInvoices,
} from '../../../hooks/useProformaInvoices';
import { fmtDate } from '../../../lib/format';
import type { ProformaInvoiceDetail } from '../../../services/proformaInvoiceService';

/**
 * "This one revises that one" (AC-E11).
 *
 * The upload's own matching is the file's numbers, applied by default - so a wrong link is
 * an easy mistake, and an expensive one to be stuck with. This is where it is corrected, and
 * it lives in the header's actions menu rather than inside the Revisions tab: it acts on the
 * whole record, and a control that only exists once you have found the right tab is a
 * control nobody finds.
 *
 * The supplier's other invoices are a PICK, never a typed identifier, and are loaded only
 * while the dialog is open.
 */
export function MarkAsRevisionDialog({
  open,
  onOpenChange,
  invoice,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  invoice: ProformaInvoiceDetail;
}) {
  const [previousId, setPreviousId] = useState<string | null>(null);
  const markAsRevision = useMarkProformaInvoiceAsRevision(invoice.id);
  const siblings = useProformaInvoices(open ? invoice.supplier_id : null, { limit: 100 });

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

  const runLink = async () => {
    if (!previousId) return;
    try {
      await markAsRevision.mutateAsync(previousId);
      onOpenChange(false);
      setPreviousId(null);
      toast.success('Linked to the document it revises.');
    } catch {
      // The hook toasts the refusal; the dialog stays open on the choice that was refused.
    }
  };

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
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
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => void runLink()} disabled={!previousId || markAsRevision.isPending}>
            Link
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

export default MarkAsRevisionDialog;
