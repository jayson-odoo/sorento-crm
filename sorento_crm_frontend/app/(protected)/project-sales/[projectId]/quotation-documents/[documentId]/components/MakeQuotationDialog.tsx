'use client';

import * as React from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Label } from '@/components/ui/label';
import { formatDateInMalaysia } from '@/lib/helpers';
import { formatMyrExact } from '../../../../_shared/lib/money';
import { useQuotationIssues } from '../../../../_shared/hooks/useQuotationDocuments';
import type {
  QuotationDocument,
  QuotationIssue,
} from '../../../../_shared/services/quotationDocumentService';

/** The printed revision, e.g. "PRJQ-2026-0003-B". */
export function issueReference(document: QuotationDocument, issue: QuotationIssue): string {
  return (
    issue.our_ref_text ??
    `${document.document_no}-${issue.revision_label ?? `R${issue.issue_no}`}`
  );
}

/**
 * PS-PROPOSAL-QUOTATION: a won project's salesperson picks ONE issued proposal revision and makes
 * it the project's quotation. Newest first, the newest preselected.
 */
export function MakeQuotationDialog({
  open,
  onOpenChange,
  projectId,
  proposal,
  isMaking,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
  proposal: QuotationDocument;
  isMaking: boolean;
  onConfirm: (issueId: string) => Promise<void>;
}) {
  const issues = useQuotationIssues(open ? projectId : undefined, open ? proposal.id : undefined);
  const rows = React.useMemo(
    () => [...(issues.data ?? [])].sort((a, b) => b.issue_no - a.issue_no),
    [issues.data],
  );
  const [picked, setPicked] = React.useState<string>('');
  React.useEffect(() => {
    if (open && rows.length > 0 && !rows.some((row) => row.id === picked)) {
      setPicked(rows[0].id);
    }
  }, [open, rows, picked]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-full max-w-md">
        <DialogHeader>
          <DialogTitle>Make quotation</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-2">
          <Label className="text-muted-foreground text-xs">From proposal revision</Label>
          {issues.isLoading ? (
            <p className="text-muted-foreground text-sm">Loading revisions...</p>
          ) : rows.length === 0 ? (
            <p className="text-muted-foreground text-sm">No revision has been sent yet.</p>
          ) : (
            <RadioGroup value={picked} onValueChange={setPicked} className="gap-2">
              {rows.map((issue) => {
                const reference = issueReference(proposal, issue);
                const id = `make-quotation-${issue.id}`;
                return (
                  <label
                    key={issue.id}
                    htmlFor={id}
                    className="has-[:checked]:border-primary has-[:checked]:bg-primary/5 flex cursor-pointer items-start gap-3 rounded-md border p-3"
                  >
                    <RadioGroupItem id={id} value={issue.id} aria-label={reference} />
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium" title={reference}>
                        {reference}
                      </span>
                      <span className="text-muted-foreground block text-xs">
                        {[
                          issue.issued_at ? formatDateInMalaysia(issue.issued_at) : null,
                          formatMyrExact(issue.grand_total),
                          issue.is_accepted ? 'signed' : null,
                        ]
                          .filter(Boolean)
                          .join(', ')}
                      </span>
                    </span>
                  </label>
                );
              })}
            </RadioGroup>
          )}
        </div>
        <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            disabled={!picked || isMaking}
            onClick={() => void onConfirm(picked)}
          >
            {isMaking ? 'Making...' : 'Make quotation'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
