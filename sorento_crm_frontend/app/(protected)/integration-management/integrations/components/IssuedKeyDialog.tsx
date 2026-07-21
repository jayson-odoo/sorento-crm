'use client';

import { useState } from 'react';
import { Check, Copy, TriangleAlert } from 'lucide-react';

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
 * outside the caller's own configuration — the server stores a hash and cannot
 * return it again.
 *
 * The dialog therefore refuses to be dismissed casually: no click-outside, no
 * Escape. Losing the key means rotating again, which for a live integration
 * means editing every place it is configured. Making that a one-stray-click
 * mistake would be a poor trade for a slightly lighter dialog.
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
    await navigator.clipboard.writeText(issued.key);
    setCopied(true);
    setAcknowledged(true);
    setTimeout(() => setCopied(false), 2000);
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
        onPointerDownOutside={(e) => e.preventDefault()}
        onEscapeKeyDown={(e) => e.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle>Copy your API key</DialogTitle>
          <DialogDescription>
            This key is shown once. It cannot be retrieved later — only replaced by
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
