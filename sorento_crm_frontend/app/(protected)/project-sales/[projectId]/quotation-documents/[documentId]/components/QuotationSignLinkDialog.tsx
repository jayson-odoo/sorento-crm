'use client';

import * as React from 'react';
import { Copy } from 'lucide-react';
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
import { Input } from '@/components/ui/input';

/**
 * The fallback for a refused clipboard.
 *
 * Copying is the normal path and needs no dialog. But `navigator.clipboard` is unavailable over
 * plain HTTP and can be blocked outright by the browser, and "Copy failed" on its own leaves the
 * user with nothing: the link they need exists and they cannot see it. So it is shown, selected on
 * focus, with the copy button offered once more.
 */
export function QuotationSignLinkDialog({
  url,
  onOpenChange,
}: {
  /** Null keeps the dialog shut. */
  url: string | null;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={Boolean(url)} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Counter-sign link</DialogTitle>
          <DialogDescription>
            Send this to the customer so they can read and accept the quotation.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input
            readOnly
            value={url ?? ''}
            aria-label="Counter-sign link"
            onFocus={(event) => event.currentTarget.select()}
          />
          <Button
            type="button"
            variant="outline"
            onClick={async () => {
              if (!url) return;
              try {
                await navigator.clipboard.writeText(url);
                toast.success('Counter-sign link copied');
              } catch {
                toast.error('Press Ctrl/Cmd+C to copy the selected link');
              }
            }}
          >
            <Copy className="size-4" aria-hidden />
            Copy
          </Button>
        </div>
        <DialogFooter>
          <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
