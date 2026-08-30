'use client';

import { useEffect } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { Check, Loader2, Copy, ExternalLink, Send } from 'lucide-react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  useContactPortalLinkMutation,
  useSendContactPortalLinkMutation,
} from '@/hooks/useContactPortalLink';
import { useCopyToClipboard } from '@/hooks/use-copy-to-clipboard';

export interface PortalLinkDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  contactId: string;
  contactLabel?: string;
  canSendViaRespondIo?: boolean;
}

function formatExpiry(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
  } catch {
    return iso;
  }
}

export default function PortalLinkDialog({
  open,
  onOpenChange,
  contactId,
  contactLabel,
  canSendViaRespondIo = true,
}: PortalLinkDialogProps) {
  const linkMutation = useContactPortalLinkMutation();
  const sendMutation = useSendContactPortalLinkMutation();

  useEffect(() => {
    if (open && contactId) {
      linkMutation.reset();
      sendMutation.reset();
      linkMutation.mutate(contactId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, contactId]);

  const { isCopied, copyToClipboard } = useCopyToClipboard();
  const data = linkMutation.data;
  const portalUrl = data?.portal_url ?? '';

  // The tick on the button is the confirmation; only a refusal needs saying (S7-05).
  async function handleCopy() {
    if (!portalUrl) return;
    if (!(await copyToClipboard(portalUrl))) toast.error('Press Ctrl/Cmd+C to copy');
  }

  async function handleSend() {
    try {
      await sendMutation.mutateAsync(contactId);
      toast.success(`Sent to ${contactLabel ?? 'contact'}`);
    } catch {
      // toast already handled in hook onError
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Portal link {contactLabel ? ` -  ${contactLabel}` : ''}</DialogTitle>
        </DialogHeader>

        {linkMutation.isPending && (
          <div className="flex items-center justify-center py-10">
            <Loader2 className="size-6 animate-spin text-muted-foreground" />
          </div>
        )}

        {linkMutation.isError && (
          <div className="space-y-2 text-sm">
            <p className="text-destructive">
              {(linkMutation.error as Error).message || 'Failed to fetch portal link.'}
            </p>
            <Button variant="outline" onClick={() => linkMutation.mutate(contactId)}>
              Retry
            </Button>
          </div>
        )}

        {data && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>Expires {formatExpiry(data.expires_at)}</span>
              {data.reused && <Badge variant="secondary">Reused existing link</Badge>}
            </div>
            <div className="flex gap-2">
              <Input value={data.portal_url} readOnly onFocus={(e) => e.currentTarget.select()} />
              <Button type="button" variant="outline" onClick={handleCopy}>
                {isCopied ? (
                  <Check className="size-4 mr-1" aria-hidden />
                ) : (
                  <Copy className="size-4 mr-1" aria-hidden />
                )}
                {isCopied ? 'Copied' : 'Copy'}
              </Button>
            </div>
            <div className="flex justify-center">
              <QRCodeSVG value={data.portal_url} size={192} marginSize={4} />
            </div>
            <div className="flex flex-col gap-2 sm:flex-row sm:justify-between">
              <Button asChild variant="outline">
                <a href={data.portal_url} target="_blank" rel="noopener noreferrer">
                  <ExternalLink className="size-4 mr-1" /> Open in new tab
                </a>
              </Button>
              <Button
                type="button"
                onClick={handleSend}
                disabled={!canSendViaRespondIo || sendMutation.isPending}
                title={
                  !canSendViaRespondIo ? 'Contact has no Respond.io ID' : undefined
                }
              >
                {sendMutation.isPending ? (
                  <Loader2 className="size-4 mr-1 animate-spin" />
                ) : (
                  <Send className="size-4 mr-1" />
                )}
                Send via Respond.io
              </Button>
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
