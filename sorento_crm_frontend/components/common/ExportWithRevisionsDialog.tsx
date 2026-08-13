'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';

/**
 * "Include revisions?" - asked once, for both the Excel and the PDF export of a
 * revisable form (round 6, 6.4).
 *
 * The caller only opens it when the question is real: the type has revisions on
 * AND this record has at least one. With nothing to include, both exports behave
 * exactly as they always have and this never appears - an option that can only
 * ever be answered one way is not a decision, it is a click.
 *
 * Checked by default: someone printing a form that HAS been revised is normally
 * asking what happened to it, and the lineage is the answer. Unchecking is one
 * click, and the export then produces precisely today's document.
 *
 * Presentation only - one dialog shared by both detail pages, so the wording and
 * the default cannot drift between them.
 */
export interface ExportWithRevisionsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** What is being exported, e.g. "Export to Excel". */
  title: string;
  /** Called with the answer. The dialog does not close itself on confirm - the
   *  caller closes it once its export has started. */
  onConfirm: (includeRevisions: boolean) => void;
  isPending?: boolean;
  confirmLabel?: string;
}

export function ExportWithRevisionsDialog({
  open,
  onOpenChange,
  title,
  onConfirm,
  isPending = false,
  confirmLabel = 'Export',
}: ExportWithRevisionsDialogProps) {
  const [includeRevisions, setIncludeRevisions] = useState(true);

  // Back to the default every time it opens: the previous answer belonged to the
  // previous export, not to this one.
  useEffect(() => {
    if (open) setIncludeRevisions(true);
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            Earlier versions are added after the current form, newest first.
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-center gap-2.5">
          <Checkbox
            id="export-include-revisions"
            data-testid="export-include-revisions"
            checked={includeRevisions}
            onCheckedChange={(checked) => setIncludeRevisions(checked === true)}
          />
          <Label htmlFor="export-include-revisions" className="cursor-pointer">
            Include revisions
          </Label>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isPending}>
            Cancel
          </Button>
          <Button onClick={() => onConfirm(includeRevisions)} disabled={isPending}>
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
