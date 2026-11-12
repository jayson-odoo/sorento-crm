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
import { QuotationAttnChooser, QuotationRecipientPicker } from './QuotationRecipientPicker';
import type {
  QuotationDocumentBody,
  QuotationDuplicateBody,
} from '../../../_shared/services/quotationDocumentService';

/**
 * QUOTE-DUPLICATE-PARTY (owner 11 Nov 2026): the same lines and prices for another party, as a
 * copy of its own. One small popup: the header's own To picker and its Attn chooser, nothing
 * else. Only the pick is sent; the server loads the party's address and contacts as the header
 * does.
 */
export function DuplicateForPartyDialog({
  open,
  onOpenChange,
  projectId,
  siteAddress,
  isSaving,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string;
  siteAddress?: string | null;
  isSaving: boolean;
  onConfirm: (body: QuotationDuplicateBody) => void;
}) {
  const [pick, setPick] = React.useState<QuotationDocumentBody>({});
  React.useEffect(() => {
    if (!open) setPick({});
  }, [open]);
  const update = (patch: QuotationDocumentBody) => setPick((previous) => ({ ...previous, ...patch }));
  const partyId = pick.recipient_party_id ?? '';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>Duplicate for another party</DialogTitle>
        </DialogHeader>
        <div className="min-w-0 space-y-3">
          <QuotationRecipientPicker
            projectId={projectId}
            siteAddress={siteAddress}
            value={pick}
            locked={false}
            onChange={update}
          />
          {partyId ? (
            <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
              <span className="min-w-0 truncate text-sm" title={pick.attn_name ?? ''}>
                Attn: {pick.attn_name || '-'}
              </span>
              <QuotationAttnChooser
                value={pick}
                partyName={pick.recipient_name_snapshot ?? ''}
                locked={false}
                autoPick
                onChange={update}
              />
            </div>
          ) : null}
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            disabled={!partyId || isSaving}
            onClick={() =>
              onConfirm({
                recipient_party_id: partyId,
                recipient_role: pick.recipient_role ?? null,
                attn_contact_ids: pick.attn_contact_ids ?? [],
              })
            }
          >
            Duplicate
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
