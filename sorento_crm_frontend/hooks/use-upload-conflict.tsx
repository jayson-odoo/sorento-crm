'use client';

import { useCallback, useRef, useState } from 'react';
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
import {
  AttachmentFilenameCollisionError,
  type AttachmentConflictResolution,
  type AttachmentFilenameCollision,
} from '@/app/(protected)/resource-management/attachments/services/attachmentService';

/**
 * Shared upload-collision UX for the Google-Drive style dup-filename rule.
 *
 * Usage:
 *   const { runUpload, ConflictDialog } = useUploadConflict();
 *   await runUpload((onConflict) => uploadMutation.mutateAsync({ ...args, onConflict }));
 *   // … render {ConflictDialog} somewhere inside your component.
 *
 * The runner re-invokes the upload with the user's choice ("replace" / "copy") on 409.
 * Cancelling rejects with the original collision error so callers can stop the batch.
 */
export function useUploadConflict() {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<AttachmentFilenameCollision | null>(null);
  const resolverRef = useRef<((choice: AttachmentConflictResolution | null) => void) | null>(null);

  const ask = useCallback(
    (incoming: AttachmentFilenameCollision) =>
      new Promise<AttachmentConflictResolution | null>((resolve) => {
        setDetail(incoming);
        setOpen(true);
        resolverRef.current = (choice) => {
          resolverRef.current = null;
          resolve(choice);
        };
      }),
    [],
  );

  const close = useCallback((choice: AttachmentConflictResolution | null) => {
    const r = resolverRef.current;
    setOpen(false);
    // Defer resolution until after the dialog unmounts so the next prompt (next file
    // in a batch) doesn't get clobbered by the closing animation.
    setTimeout(() => r?.(choice), 0);
  }, []);

  const runUpload = useCallback(
    async <T,>(perform: (onConflict?: AttachmentConflictResolution) => Promise<T>): Promise<T | null> => {
      try {
        return await perform();
      } catch (err) {
        if (!(err instanceof AttachmentFilenameCollisionError)) throw err;
        const choice = await ask(err.detail);
        if (choice == null) {
          return null;
        }
        return await perform(choice);
      }
    },
    [ask],
  );

  const ConflictDialog = (
    <AlertDialog open={open} onOpenChange={(o) => !o && close(null)}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>File already exists in this folder</AlertDialogTitle>
          <AlertDialogDescription>
            An attachment named <strong>{detail?.existing_file_name ?? ''}</strong> already exists.
            Replace the existing file (its links to packing lists, promotions, products and forms stay
            valid) or upload a renamed copy?
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={() => close(null)}>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={() => close('copy')}>Create copy</AlertDialogAction>
          <AlertDialogAction
            onClick={() => close('replace')}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            Replace existing
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );

  return { runUpload, ConflictDialog };
}
