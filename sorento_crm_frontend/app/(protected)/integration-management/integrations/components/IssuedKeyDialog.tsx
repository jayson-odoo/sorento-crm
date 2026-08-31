'use client';

import { useState } from 'react';
import { Check, Copy, TriangleAlert } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import type { IssuedKey } from '../types/integration.types';

/**
 * Shows a freshly minted key. This is the only moment it exists anywhere
 * outside the caller's own configuration - the server stores a hash and cannot
 * return it again.
 *
 * The dialog therefore refuses to be dismissed casually before the key is
 * copied: no click-outside, no Escape. Losing the key means rotating again,
 * which for a live integration means editing every place it is configured.
 * Making that a one-stray-click mistake would be a poor trade for a slightly
 * lighter dialog. Once the key is copied (`acknowledged`), both guards stand
 * down - Escape and click-outside close it like any other dialog, so the
 * gate never becomes a permanent keyboard trap (S9-02).
 */
export function IssuedKeyDialog({
  issued,
  onClose,
}: {
  issued: IssuedKey | null;
  onClose: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);

  if (!issued) return null;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(issued.key);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard write can fail (permission denied, insecure context, etc).
      // The key is still visible and selectable in the dialog, so let the
      // user copy it by hand instead of trapping them behind the guard.
      toast.error('Could not copy automatically. Select the key and copy it manually.');
    } finally {
      setAcknowledged(true);
    }
  };

  const close = () => {
    setCopied(false);
    setAcknowledged(false);
    onClose();
  };

  return (
    <Dialog open onOpenChange={(open) => !open && acknowledged && close()}>
      <DialogContent
        className="max-h-[90vh] overflow-y-auto sm:max-w-lg"
        onPointerDownOutside={(e) => {
          if (!acknowledged) e.preventDefault();
        }}
        onEscapeKeyDown={(e) => {
          if (!acknowledged) e.preventDefault();
        }}
        // Hidden until the key is copied. Browser verification caught the X
        // still rendering while the guard silently swallowed its click -- a
        // control that looks live and does nothing reads as a broken app, and
        // the user retries instead of copying the key they are about to lose.
        showCloseButton={acknowledged}
      >
        <DialogHeader>
          <DialogTitle>Copy your API key</DialogTitle>
          <DialogDescription>
            This key is shown once. It cannot be retrieved later - only replaced by
            rotating it.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-200">
            <TriangleAlert className="mt-0.5 size-4 shrink-0" />
            <span>
              Store it in your integration&apos;s configuration now. If you close this
              without copying it, you will need to rotate the key and update every place
              it is configured.
            </span>
          </div>

          <div className="flex items-center gap-2">
            <code className="min-w-0 flex-1 truncate rounded-md bg-muted px-3 py-2 font-mono text-sm">
              {issued.key}
            </code>
            <Button variant="outline" size="sm" onClick={copy} aria-label="Copy API key">
              {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
            </Button>
          </div>
        </div>

        <DialogFooter>
          <Button onClick={close} disabled={!acknowledged}>
            {acknowledged ? 'Done' : 'Copy the key first'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
