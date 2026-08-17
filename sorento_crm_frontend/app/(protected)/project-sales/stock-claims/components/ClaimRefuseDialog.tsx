'use client';

import * as React from 'react';
import { LoaderCircleIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import type { AllocationClaimRow } from '../../_shared/types/projectAllocation.types';
import { formatQty } from '../../[projectId]/components/SalesOrderMoney';

/**
 * Refusing a stock claim, with the reason that makes it usable (AC-H4).
 *
 * The reason is mandatory here and again on the server. A refusal with none tells the
 * asking CS nothing except to pick up the phone, which is what the claim replaced.
 */
export function ClaimRefuseDialog({
  claim,
  submitting,
  onDone,
  onRefuse,
}: {
  claim: AllocationClaimRow;
  submitting: boolean;
  onDone: () => void;
  onRefuse: (reason: string) => Promise<unknown>;
}) {
  const [reason, setReason] = React.useState('');
  const trimmed = reason.trim();

  const submit = async () => {
    if (trimmed.length < 3) return;
    await onRefuse(trimmed);
    onDone();
  };

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Refuse this claim</DialogTitle>
          <DialogDescription>
            {`${claim.from_project_code} asked for ${formatQty(claim.qty)} ${
              claim.product_code || 'of this product'
            } at ${claim.warehouse_code || 'this location'}.`}
          </DialogDescription>
        </DialogHeader>

        <DialogBody className="space-y-2">
          <Label htmlFor="claim-refusal-reason">Why the stock cannot be released</Label>
          <Textarea
            id="claim-refusal-reason"
            rows={4}
            value={reason}
            placeholder="Committed to our own hand-over in July."
            onChange={(event) => setReason(event.target.value)}
          />
          <p className="text-xs text-muted-foreground">
            {`${claim.from_project_cs_name || 'The asking CS'} sees this on the line.`}
          </p>
        </DialogBody>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={onDone} disabled={submitting}>
            Cancel
          </Button>
          <Button
            type="button"
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            disabled={submitting || trimmed.length < 3}
            onClick={submit}
          >
            {submitting && <LoaderCircleIcon className="size-4 animate-spin" aria-hidden />}
            Refuse
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
