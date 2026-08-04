'use client';

import * as React from 'react';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { SignaturePad, type SignatureValue } from '@/components/common/SignaturePad';
import type { QuotationSignatureBody } from '../../../../_shared/services/quotationDocumentService';

/**
 * The project owner's signature on the DRAFT, in a modal (the CRUD standard's default).
 *
 * The pad commits only on Apply, so this dialog does no confirming of its own: pressing Apply IS
 * the confirmation, and a second "are you sure" over it would just add a click to the one action
 * the user came here for.
 */
export function QuotationSignDialog({
  open,
  onOpenChange,
  signatoryName,
  isSaving,
  onSign,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Prefills Type mode and seeds Initials: a known signatory is never asked for their name. */
  signatoryName: string | null;
  isSaving: boolean;
  onSign: (body: QuotationSignatureBody) => void;
}) {
  const handleChange = (value: SignatureValue | null) => {
    // Null is Clear, which is a local act on the pad and nothing to send.
    if (!value) return;
    onSign({
      signer_name: value.typedText ?? signatoryName,
      mode: value.mode,
      image_data_uri: value.dataUrl,
      // Strings, not JSON numbers: the column is NUMERIC(10,7).
      gps_lat: value.gpsLat === null ? null : String(value.gpsLat),
      gps_lng: value.gpsLng === null ? null : String(value.gpsLng),
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Sign this quotation</DialogTitle>
          <DialogDescription>
            Draw, type or initial. Applying records the time, your address and, when your browser
            offers it, your location.
          </DialogDescription>
        </DialogHeader>
        <DialogBody>
          <SignaturePad
            label="Your signature"
            commitLabel="Apply signature"
            typedNameDefault={signatoryName ?? ''}
            disabled={isSaving}
            onChange={handleChange}
          />
          {isSaving && (
            <p className="mt-3 text-sm text-muted-foreground">Saving the signature...</p>
          )}
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}
