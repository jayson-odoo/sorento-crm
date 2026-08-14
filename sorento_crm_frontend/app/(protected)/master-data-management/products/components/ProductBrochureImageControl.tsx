'use client';

import { useState } from 'react';
import { ImageOff, ImagePlus, ImageUp, LoaderCircleIcon } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
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

const IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tif', '.tiff'];

/**
 * A product's attachments include 532 spec-sheet PDFs in the live data, and a
 * spec sheet rendered as the product photo is worse than no photo, so only
 * images may be offered. Falls back to the extension because a good part of the
 * older rows carry no mime type.
 */
export function isImageAttachment(
  mimeType: string | null | undefined,
  filename: string | null | undefined,
): boolean {
  if (mimeType?.toLowerCase().startsWith('image/')) return true;
  if (mimeType) return false;
  const name = (filename ?? '').toLowerCase();
  return IMAGE_EXTENSIONS.some((ext) => name.endsWith(ext));
}

/** The visible mark, rendered beside the filename so a scan of the list finds it. */
export function BrochureImageBadge() {
  return <Badge variant="primary">Brochure image</Badge>;
}

interface ProductBrochureImageControlProps {
  isChosen: boolean;
  isSaving: boolean;
  isClearing: boolean;
  onChoose: () => void;
  onClear: () => void;
}

export default function ProductBrochureImageControl({
  isChosen,
  isSaving,
  isClearing,
  onChoose,
  onClear,
}: ProductBrochureImageControlProps) {
  const [confirmClearOpen, setConfirmClearOpen] = useState(false);

  if (!isChosen) {
    return (
      <Button
        type="button"
        variant="ghost"
        size="sm"
        aria-label="Use as brochure image"
        title="Use as brochure image"
        onClick={onChoose}
        disabled={isSaving}
      >
        {isSaving ? (
          <LoaderCircleIcon className="size-4 animate-spin" />
        ) : (
          <ImagePlus className="size-4" />
        )}
      </Button>
    );
  }

  return (
    <>
      {/* Disabled rather than absent: the chosen row still shows where the mark
          lives, and a second click can never leave the product with nothing. */}
      <Button
        type="button"
        variant="ghost"
        size="sm"
        aria-label="Already the brochure image"
        title="Already the brochure image"
        disabled
      >
        <ImageUp className="size-4 text-primary" />
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        aria-label="Clear brochure image"
        title="Clear brochure image"
        onClick={() => setConfirmClearOpen(true)}
        disabled={isClearing}
      >
        {isClearing ? (
          <LoaderCircleIcon className="size-4 animate-spin" />
        ) : (
          <ImageOff className="size-4 text-destructive" />
        )}
      </Button>
      <AlertDialog open={confirmClearOpen} onOpenChange={setConfirmClearOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Clear brochure image?</AlertDialogTitle>
            <AlertDialogDescription>
              The file stays attached. Choose another photo when you are ready.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isClearing}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={(e) => {
                e.preventDefault();
                onClear();
                setConfirmClearOpen(false);
              }}
              disabled={isClearing}
            >
              Clear
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
