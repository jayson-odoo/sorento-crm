'use client';

import * as React from 'react';
import { Check, Copy } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { toast } from '@/lib/toast';
import { useCopyToClipboard } from '@/hooks/use-copy-to-clipboard';
import { waMeUrl } from '@/lib/wa-me';
import { QuotationSignLinkDialog } from './QuotationSignLinkDialog';
import { useQuotationDocumentMutations } from '../../../../_shared/hooks/useQuotationDocuments';
import {
  pickMobile,
  quotationNumberLabel,
  toWaDigits,
  whatsAppMessage,
} from '../../../../_shared/lib/quotationWhatsApp';
import type {
  QuotationDocument,
  QuotationIssue,
} from '../../../../_shared/services/quotationDocumentService';

/**
 * The prompt that hands a sent quotation to the salesperson's own WhatsApp.
 *
 * Nothing is sent from here: "Open WhatsApp" is a wa.me link with the chat and the text already
 * filled in, and the salesperson presses Send in WhatsApp. The number and the message are local
 * to this prompt and never reach the server; only the fact that the link was opened is logged.
 *
 * Open while it holds an issue. The body is mounted per open, so reopening starts from the
 * template again.
 */
export function QuotationWhatsAppDialog({
  projectId,
  document,
  issue,
  onOpenChange,
}: {
  projectId: string;
  document: QuotationDocument;
  /** Null keeps the dialog shut. */
  issue: QuotationIssue | null;
  onOpenChange: (open: boolean) => void;
}) {
  // The last issue stays on screen while the close animation runs; Radix unmounts the body (and
  // its state) once the exit finishes, so a reopen starts from the template again.
  const lastIssue = React.useRef<QuotationIssue | null>(null);
  if (issue) lastIssue.current = issue;
  const shown = issue ?? lastIssue.current;
  return (
    <Dialog open={Boolean(issue)} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg" aria-describedby={undefined}>
        {shown && (
          <WhatsAppBody
            projectId={projectId}
            document={document}
            key={shown.id}
            issue={shown}
            onClose={() => onOpenChange(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function WhatsAppBody({
  projectId,
  document,
  issue,
  onClose,
}: {
  projectId: string;
  document: QuotationDocument;
  issue: QuotationIssue;
  onClose: () => void;
}) {
  const mutations = useQuotationDocumentMutations(projectId, document.id);
  const { isCopied, copyToClipboard } = useCopyToClipboard();
  const [link, setLink] = React.useState<string | null>(null);
  const [failed, setFailed] = React.useState(false);
  const [to, setTo] = React.useState(() => {
    const digits = pickMobile(document.recipient_phone_snapshot);
    return digits ? `+${digits}` : '';
  });
  const [edited, setEdited] = React.useState<string | null>(null);
  const [linkToShow, setLinkToShow] = React.useState<string | null>(null);
  const messageRef = React.useRef<HTMLTextAreaElement>(null);
  const mintedFor = React.useRef<string | null>(null);

  // One open mints once: StrictMode runs the effect twice, a new issue mints again.
  const { mutateAsync: mint } = mutations.signLink;
  React.useEffect(() => {
    if (mintedFor.current === issue.id) return;
    mintedFor.current = issue.id;
    mint({ id: document.id, issueId: issue.id }).then(
      // The server returns a relative path; the origin is whichever one this screen runs on.
      (result) => setLink(`${window.location.origin}${result.path}`),
      () => setFailed(true),
    );
  }, [mint, document.id, issue.id]);

  const message =
    edited ??
    (link
      ? whatsAppMessage({
          attn: document.attn_name,
          numberLabel: quotationNumberLabel(document, issue),
          subject: document.subject_title,
          link,
          signatory: document.signatory_name?.trim() || document.signatory_signature?.signer_name?.trim(),
        })
      : '');
  const ready = link !== null;

  return (
    <>
      <DialogHeader>
        <DialogTitle>{`Send R${issue.issue_no} via WhatsApp`}</DialogTitle>
      </DialogHeader>
      <div className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="quotation-whatsapp-to">To</Label>
          <Input
            id="quotation-whatsapp-to"
            type="tel"
            inputMode="tel"
            value={to}
            onChange={(event) => setTo(event.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="quotation-whatsapp-message">Message</Label>
          <Textarea
            id="quotation-whatsapp-message"
            ref={messageRef}
            rows={9}
            value={message}
            disabled={!ready}
            onChange={(event) => setEdited(event.target.value)}
          />
        </div>
        {failed && (
          <p role="alert" className="text-sm text-destructive">
            Could not create the counter-sign link.
          </p>
        )}
      </div>
      <DialogFooter className="gap-2 sm:gap-0">
        <Button type="button" variant="ghost" onClick={onClose}>
          Close
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={!ready}
          onClick={async () => {
            if (!link || (await copyToClipboard(link))) return;
            // Clipboard refused: select the link in the message so Ctrl/Cmd+C finishes the job.
            const box = messageRef.current;
            const start = box ? box.value.indexOf(link) : -1;
            if (!box || start < 0) {
              // The link was edited out of the message: show it where it can be copied by hand.
              setLinkToShow(link);
              return;
            }
            box.focus();
            box.setSelectionRange(start, start + link.length);
            toast.error('Press Ctrl/Cmd+C to copy the selected link');
          }}
        >
          {isCopied ? (
            <Check className="size-4" aria-hidden />
          ) : (
            <Copy className="size-4" aria-hidden />
          )}
          {isCopied ? 'Copied' : 'Copy link'}
        </Button>
        <Button asChild>
          <a
            href={ready ? waMeUrl(toWaDigits(to), message) : undefined}
            target="_blank"
            rel="noopener noreferrer"
            aria-disabled={ready ? undefined : true}
            className={ready ? undefined : 'pointer-events-none opacity-50'}
            onClick={(event) => {
              if (!ready) {
                event.preventDefault();
                return;
              }
              // Fired and forgotten: opening WhatsApp must never wait on, or fail with, the note.
              mutations.whatsAppOpened.mutate({ id: document.id, issueId: issue.id });
            }}
          >
            Open WhatsApp
          </a>
        </Button>
      </DialogFooter>
      <QuotationSignLinkDialog url={linkToShow} onOpenChange={() => setLinkToShow(null)} />
    </>
  );
}
