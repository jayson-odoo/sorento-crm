'use client';

import { useState } from 'react';
import { HandHelping } from 'lucide-react';

import { DropdownMenuItem } from '@/components/ui/dropdown-menu';
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
import type { HandlingLockState } from './handlingLock';

/**
 * Gear-dropdown item to RELEASE the handling lock. Only the current holder can release
 * (state === 'mine'); the backend enforces the same holder-only rule. Render inside the
 * form's actions DropdownMenu, next to "Escalate SLA" / "Extend SLA".
 *
 * Releasing is a detach, so it routes through a confirm dialog (never one-click, per the
 * "confirm before delete OR unlink" standard). `onSelect` preventDefaults to keep the
 * menu mounted while the dialog is open.
 */
export function HandlingLockReleaseMenuItem({
  state,
  onRelease,
}: {
  state: HandlingLockState;
  onRelease: () => void;
}) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  if (state !== 'mine') return null;
  return (
    <>
      <DropdownMenuItem
        onSelect={(e) => {
          e.preventDefault();
          setConfirmOpen(true);
        }}
      >
        <HandHelping className="size-4" />
        Unclaim
      </DropdownMenuItem>
      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Unclaim this form?</AlertDialogTitle>
            <AlertDialogDescription>
              This form will be open for any eligible team member to handle again, and its
              action buttons will lock until someone claims it. You can re-claim it any time.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                onRelease();
                setConfirmOpen(false);
              }}
            >
              Unclaim
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

/**
 * Confirm dialog for taking over an ACTIVE handler. Non-destructive styling (default
 * primary action) — this is a handover, not a delete. Copy names the current holder so
 * the actor knows who they're displacing (PLAN §5 / P1-9).
 */
export function TakeOverConfirmDialog({
  open,
  onOpenChange,
  handlerName,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  handlerName?: string | null;
  onConfirm: () => void;
}) {
  const who = handlerName?.trim() || 'Someone';
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Take over handling?</AlertDialogTitle>
          <AlertDialogDescription>
            <span className="font-medium">{who}</span> is currently handling this. Taking
            over makes you the handler so you can act on this form. They will be notified.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={(e) => {
              e.preventDefault();
              onConfirm();
              onOpenChange(false);
            }}
          >
            Take over handling
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
