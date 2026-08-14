'use client';

import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import {
  setBrochureImage,
  clearBrochureImage,
} from '../services/productBrochureImageService';
import type { ProductAttachment } from '../../product-attachments/types/productAttachment.types';

interface UseProductBrochureImageResult {
  /** The single attachment currently acting as the brochure image, or null. */
  chosenAttachmentId: string | null;
  chooseBrochureImage: (attachmentId: string) => void;
  clearChosenBrochureImage: () => void;
  isSaving: boolean;
  /** The attachment whose save is in flight, so only its own control spins. */
  savingAttachmentId: string | null;
  isClearing: boolean;
}

/**
 * Owns the brochure-image choice for one product.
 *
 * The choice is derived as a SINGLE id rather than read per row, so the UI is
 * structurally incapable of showing two marks at once even if the API ever
 * returned two flagged rows (which is the exact bug this feature removes).
 */
export function useProductBrochureImage(
  productId: string | null | undefined,
  attachments: ProductAttachment[] | undefined,
): UseProductBrochureImageResult {
  const queryClient = useQueryClient();

  const serverChoice = useMemo(() => {
    const flagged = (attachments ?? []).find((pa) => pa.is_primary);
    return flagged?.attachment?.id ?? flagged?.attachment_id ?? null;
  }, [attachments]);

  // `undefined` means "no local opinion, show what the server says". A saved
  // choice is held only until the refetch reports the same thing, so the mark
  // moves on the click instead of waiting a round trip.
  const [savedChoice, setSavedChoice] = useState<string | null | undefined>(undefined);

  useEffect(() => {
    setSavedChoice((prev) => (prev === serverChoice ? undefined : prev));
  }, [serverChoice]);

  const chosenAttachmentId = savedChoice !== undefined ? savedChoice : serverChoice;

  const invalidateAttachmentLists = () => {
    queryClient.invalidateQueries({ queryKey: ['product-attachments-by-product', productId] });
    queryClient.invalidateQueries({ queryKey: ['product-attachments'] });
  };

  const chooseMutation = useMutation({
    mutationFn: (attachmentId: string) => setBrochureImage(productId!, attachmentId),
    onSuccess: (_data, attachmentId) => {
      setSavedChoice(attachmentId);
      invalidateAttachmentLists();
      toast.success('Brochure image updated');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to set the brochure image');
    },
  });

  const clearMutation = useMutation({
    mutationFn: () => clearBrochureImage(productId!),
    onSuccess: () => {
      setSavedChoice(null);
      invalidateAttachmentLists();
      toast.success('Brochure image cleared');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to clear the brochure image');
    },
  });

  return {
    chosenAttachmentId,
    chooseBrochureImage: (attachmentId: string) => {
      if (!productId || attachmentId === chosenAttachmentId) return;
      chooseMutation.mutate(attachmentId);
    },
    clearChosenBrochureImage: () => {
      if (!productId) return;
      clearMutation.mutate();
    },
    isSaving: chooseMutation.isPending,
    savingAttachmentId: chooseMutation.isPending ? (chooseMutation.variables ?? null) : null,
    isClearing: clearMutation.isPending,
  };
}
