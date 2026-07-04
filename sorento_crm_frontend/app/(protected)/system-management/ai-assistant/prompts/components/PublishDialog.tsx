'use client';

import { Loader2 } from 'lucide-react';
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

/**
 * Confirm dialog for moving a label to a version (publish / rollback). AlertDialog
 * per CRUD UX standard — never confirm() (feedback_confirm_before_delete_or_unlink).
 */
export function PublishDialog({
  open,
  onOpenChange,
  keyName,
  version,
  label,
  pending,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  keyName: string;
  version: number | null;
  label: 'production' | 'staging';
  pending: boolean;
  onConfirm: () => void;
}) {
  const isProd = label === 'production';
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            Publish {keyName} v{version} to {label}?
          </AlertDialogTitle>
          <AlertDialogDescription>
            {isProd
              ? 'This changes the live assistant immediately. The very next chat turn will use this version.'
              : 'This moves the staging label. Use the dry-run box to test before publishing to production.'}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={(e) => {
              e.preventDefault();
              onConfirm();
            }}
            disabled={pending}
            className={isProd ? 'bg-destructive text-destructive-foreground hover:bg-destructive/90' : undefined}
          >
            {pending ? <Loader2 className="size-4 animate-spin" /> : `Publish to ${label}`}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
