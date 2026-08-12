'use client';

import { LoaderCircleIcon } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { useResubmitPromotionFlyers } from '../hooks/usePromotions';
import type { Promotion } from '../types/promotion.types';

interface PromotionBulkResubmitDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The selected rows, so the linked flyer attachments can be resolved client-side. */
  promotions: Promotion[];
  onSuccess?: () => void;
}

interface ResubmitSplit {
  eligible: Promotion[];
  noAttachment: Promotion[];
  multiAttachment: Promotion[];
}

/**
 * A promotion is only safely re-extractable when it has exactly one flyer.
 *
 * n8n receives one webhook per attachment and posts back a payload naming only that
 * attachment, and the external create endpoint rebuilds the promotion from that
 * payload - dropping every existing group AND every existing attachment link before
 * re-adding what the payload carries. On a promotion with two flyers, re-extracting
 * one therefore unlinks the other. Skipping is the honest option until the backend can
 * merge multi-flyer extractions.
 */
export function splitPromotionsForResubmit(promotions: Promotion[]): ResubmitSplit {
  const eligible: Promotion[] = [];
  const noAttachment: Promotion[] = [];
  const multiAttachment: Promotion[] = [];
  for (const promotion of promotions) {
    const count = (promotion.attachments ?? []).length;
    if (count === 1) eligible.push(promotion);
    else if (count === 0) noAttachment.push(promotion);
    else multiAttachment.push(promotion);
  }
  return { eligible, noAttachment, multiAttachment };
}

export default function PromotionBulkResubmitDialog({
  open,
  onOpenChange,
  promotions,
  onSuccess,
}: PromotionBulkResubmitDialogProps) {
  const resubmitMutation = useResubmitPromotionFlyers();
  const { eligible, noAttachment, multiAttachment } = splitPromotionsForResubmit(promotions);
  const attachmentIds = eligible.map((p) => (p.attachments ?? [])[0].attachment_id);

  const handleResubmit = () => {
    if (attachmentIds.length === 0) return;
    resubmitMutation.mutate(attachmentIds, {
      // The mutation resolves even when every flyer failed (it tallies rather than
      // throws), so dismissing has to be conditional - otherwise a total failure
      // closes the dialog and drops the selection, leaving nothing to retry from.
      onSuccess: ({ succeeded }) => {
        if (succeeded === 0) return;
        onOpenChange(false);
        onSuccess?.();
      },
    });
  };

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Resubmit</AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="space-y-2">
              <p>
                Re-extract {eligible.length} promotion{eligible.length !== 1 ? 's' : ''}?
                Existing groups and products are replaced. This cannot be undone.
              </p>
              {noAttachment.length > 0 && (
                <p className="text-muted-foreground">
                  Skipping {noAttachment.length} promotion
                  {noAttachment.length !== 1 ? 's' : ''} with no flyer attached.
                </p>
              )}
              {multiAttachment.length > 0 && (
                <p className="text-muted-foreground">
                  Skipping {multiAttachment.length} promotion
                  {multiAttachment.length !== 1 ? 's' : ''} with more than one flyer:
                  re-extracting one flyer would unlink the others.
                </p>
              )}
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={resubmitMutation.isPending}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={(e) => {
              e.preventDefault();
              handleResubmit();
            }}
            disabled={resubmitMutation.isPending || eligible.length === 0}
          >
            {resubmitMutation.isPending && (
              <LoaderCircleIcon className="size-4 animate-spin mr-2" />
            )}
            Resubmit {eligible.length}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
