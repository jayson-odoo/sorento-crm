'use client';

import * as React from 'react';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import type { FindingSeverity } from '../../_shared/types/projectSalesOrder.types';
import { FINDING_SEVERITY_BADGE_VARIANT, FINDING_SEVERITY_LABEL } from '../../_shared/lib/findings';

/**
 * The one dismiss dialog every review screen opens, for every severity (R3, R20): a reason
 * is mandatory, at least 3 characters, and the confirm button names how many underlying
 * findings this row's Dismiss clears. The two-tier gate itself is unchanged and enforced by
 * the server - a hard finding's dismiss is still refused there without
 * projects.projects.manage - so there is no second, in-page confirmation step here.
 */
export function DismissReasonDialog({
  severity,
  detail,
  ids,
  onDone,
  onDismiss,
  submitting,
}: {
  severity: FindingSeverity;
  detail: string;
  ids: string[];
  onDone: () => void;
  onDismiss: (ids: string[], reason: string) => Promise<unknown>;
  submitting: boolean;
}) {
  const [reason, setReason] = React.useState('');
  const trimmed = reason.trim();
  const count = ids.length;
  const canSubmit = trimmed.length >= 3 && !submitting;

  const submit = async () => {
    if (!canSubmit) return;
    await onDismiss(ids, trimmed);
    onDone();
  };

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92vh] w-full max-w-md overflow-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            Dismiss with a reason
            <Badge variant={FINDING_SEVERITY_BADGE_VARIANT[severity]} appearance="light">
              {FINDING_SEVERITY_LABEL[severity]}
            </Badge>
          </DialogTitle>
          <DialogDescription>
            {count > 1 ? `${detail} ${count} lines affected.` : detail}
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={async (event) => {
            event.preventDefault();
            await submit();
          }}
        >
          <DialogBody className="max-h-[60vh] space-y-4 overflow-y-auto">
            <div className="space-y-1.5">
              <Label htmlFor="dismiss-reason">
                Reason <span className="text-destructive">*</span>
              </Label>
              <Textarea
                id="dismiss-reason"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                rows={4}
                placeholder="In your own words"
              />
            </div>
          </DialogBody>

          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" onClick={onDone}>
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {submitting ? 'Dismissing…' : `Dismiss ${count}`}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
