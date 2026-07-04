'use client';

import { useState, useRef, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { toast } from 'sonner';
import { Send, Link2, LayoutTemplate, FileText, Info } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Skeleton } from '@/components/ui/skeleton';
import SendTemplateDialog from '@/components/common/whatsapp-template/SendTemplateDialog';
import { useConversationWindowState } from './useConversationWindowState';
import {
  sendConversationMessage,
  getChatTemplatePreview,
  NoChatTemplateError,
} from '@/services/whatsappTemplateService';

interface SharedConversationComposerProps {
  /** 'complaint' | 'stock_inquiry' | 'purchase_request' | 'sponsorship_form' | 'conversation_sla' */
  entityType: string;
  entityId: string;
  canReply: boolean;
  /** 'entity' shows view-link + "Use response" affordances; 'conversation' (form-less) hides them. */
  mode?: 'entity' | 'conversation';
  /** entity-mode: text offered by the "Use response" button (technical/purchasing reply). */
  useResponseText?: string | null;
  useResponseLabel?: string;
  /** entity-mode: resolves a portal/view link to append to the draft. */
  onGetViewLink?: () => Promise<string>;
  /** When `key` changes, replaces the compose field with `text` (e.g. after "Update & Reply"). */
  replyComposePrefill?: { key: number; text: string } | null;
  /** Called after a successful send so the parent can refetch the chat list. */
  onSent?: () => void;
  /** Shown when !canReply. Entity-specific copy; defaults to a generic message. */
  notAvailableMessage?: string;
}

/**
 * Unified chat-window composer shared by every conversation surface. A pure
 * message send: the backend decides plain-vs-template by the 24h window.
 *
 * - IN-WINDOW: a normal textbox; the raw typed text is delivered verbatim.
 * - OUT-OF-WINDOW: the form's `*_chat` template is rendered inline with its
 *   non-message parts pre-filled and an editable field where the message goes —
 *   so you see exactly what the contact receives and only fill in the message.
 *
 * Never mutates the entity, never blocks on the window.
 */
export default function SharedConversationComposer({
  entityType,
  entityId,
  canReply,
  mode = 'entity',
  useResponseText,
  useResponseLabel = 'Use response',
  onGetViewLink,
  replyComposePrefill,
  onSent,
  notAvailableMessage = 'Reply is only available when a Respond.io conversation is linked to this record.',
}: SharedConversationComposerProps) {
  const [replyText, setReplyText] = useState('');
  const [sending, setSending] = useState(false);
  const [viewLinkLoading, setViewLinkLoading] = useState(false);
  const [templateDialogOpen, setTemplateDialogOpen] = useState(false);
  const [sendError, setSendError] = useState<{ message: string; settingsUrl: string } | null>(null);
  const replyTextareaRef = useRef<HTMLTextAreaElement>(null);
  const appliedPrefillKeyRef = useRef(0);

  const { windowClosed } = useConversationWindowState(entityType, entityId, canReply);
  const isEntity = mode === 'entity';

  // Out-of-window: fetch the form's chat template so we can render it inline with
  // a fill-in field. DB-only on the backend — no Respond call.
  const { data: preview, isLoading: previewLoading } = useQuery({
    queryKey: ['chat-template-preview', entityType, entityId],
    queryFn: () => getChatTemplatePreview(entityType, entityId),
    enabled: canReply && windowClosed,
    staleTime: 60_000,
  });

  const templateMode = windowClosed && !!preview?.configured;
  const noTemplateConfigured = windowClosed && preview !== undefined && !preview.configured;

  useEffect(() => {
    if (!replyComposePrefill) return;
    if (replyComposePrefill.key === appliedPrefillKeyRef.current) return;
    appliedPrefillKeyRef.current = replyComposePrefill.key;
    setReplyText(replyComposePrefill.text);
    queueMicrotask(() => replyTextareaRef.current?.focus());
  }, [replyComposePrefill]);

  const onDraftChange = (value: string) => {
    setReplyText(value);
    if (sendError) setSendError(null);
  };

  const handleSend = async () => {
    const text = replyText.trim();
    if (!text || sending || !canReply) return;
    setSending(true);
    setSendError(null);
    try {
      const result = await sendConversationMessage(entityType, entityId, text);
      setReplyText('');
      toast.success(result.sent_as === 'template' ? 'Delivered as a template message' : 'Message sent');
      // Pulse a few more refetches so the outgoing message's delivery status
      // (clock → sent/delivered/read ticks) catches up as Respond posts receipts.
      onSent?.();
      [6000, 15000].forEach((delay) => window.setTimeout(() => onSent?.(), delay));
    } catch (err) {
      if (err instanceof NoChatTemplateError) {
        setSendError({ message: err.message, settingsUrl: err.settingsUrl });
      } else {
        toast.error(err instanceof Error ? err.message : 'Failed to send message');
      }
    } finally {
      setSending(false);
    }
  };

  if (!canReply) {
    return <p className="text-xs text-muted-foreground">{notAvailableMessage}</p>;
  }

  const noTemplateNotice = (settingsUrl: string, message: string) => (
    <div
      className="flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-200"
      data-testid="no-chat-template-notice"
    >
      <Info className="size-3.5 mt-0.5 shrink-0" />
      <div>
        {message}{' '}
        <Link href={settingsUrl} className="font-medium underline">
          Configure a chat reply template
        </Link>
        , or use “Send template” below.
      </div>
    </div>
  );

  const sendButton = (
    <Button
      size="icon"
      className="shrink-0"
      disabled={!replyText.trim() || sending}
      onClick={handleSend}
      aria-label="Send"
    >
      <Send className="size-4" />
    </Button>
  );

  // Split the template body into text + slot tokens so we can render the message
  // slot as an editable field and the rest as resolved, read-only text.
  const renderTemplateBody = () => {
    const body = preview?.body_text ?? '';
    const parts = body.split(/(\{\{\d+\}\})/g);
    return parts.map((part, idx) => {
      const m = part.match(/^\{\{(\d+)\}\}$/);
      if (!m) return <span key={idx}>{part}</span>;
      const slot = preview?.slots?.[m[1]];
      if (slot?.editable) {
        return (
          <Textarea
            key={idx}
            ref={replyTextareaRef}
            data-testid="template-message-field"
            placeholder="Type your message…"
            value={replyText}
            onChange={(e) => onDraftChange(e.target.value)}
            rows={2}
            disabled={sending}
            className="my-1 block w-full resize-none bg-background"
          />
        );
      }
      // Non-message slot: resolved value (or the raw token if unresolved).
      return (
        <span key={idx} className="font-medium">
          {slot?.value ?? part}
        </span>
      );
    });
  };

  return (
    <div className="space-y-2">
      {/* ---- Out-of-window, template configured: inline template-fill ---- */}
      {templateMode ? (
        <div className="space-y-2" data-testid="composer-template-mode">
          <div className="flex items-start gap-2 text-xs text-muted-foreground">
            <LayoutTemplate className="size-3.5 mt-0.5 shrink-0" />
            <span>
              Outside the 24h window — this is sent as the template
              {preview?.template_name ? ` “${preview.template_name}”` : ''}. Fill in your message
              below; line breaks are removed in template messages.
            </span>
          </div>
          <div className="rounded-md border bg-muted/30 p-3 text-sm whitespace-pre-wrap break-words">
            {renderTemplateBody()}
          </div>
          {/[\n\t]|\s{2,}/.test(replyText) && (
            <p className="text-xs text-amber-600 dark:text-amber-400" data-testid="flatten-warning">
              Line breaks, tabs and repeated spaces are removed when sent as a template — the
              message is delivered on one line.
            </p>
          )}
          <div className="flex justify-end">{sendButton}</div>
        </div>
      ) : noTemplateConfigured ? (
        /* ---- Out-of-window, no template configured ---- */
        noTemplateNotice(
          preview?.settings_url ?? '/integration-management/whatsapp-templates',
          'No chat reply template configured for this form.',
        )
      ) : windowClosed && previewLoading ? (
        /* ---- Out-of-window, loading the template ---- */
        <Skeleton className="h-20 w-full" />
      ) : (
        /* ---- In-window: normal textbox (raw typed text) ---- */
        <div className="flex gap-2">
          <Textarea
            ref={replyTextareaRef}
            placeholder="Type your message..."
            value={replyText}
            onChange={(e) => onDraftChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            rows={3}
            disabled={sending}
            className="resize-none flex-1 min-w-0"
          />
          {sendButton}
        </div>
      )}

      {/* Send-time no_chat_template fallback (rare race after preview said OK). */}
      {sendError && noTemplateNotice(sendError.settingsUrl, sendError.message)}

      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant={windowClosed ? 'primary' : 'outline'}
          size="sm"
          onClick={() => setTemplateDialogOpen(true)}
        >
          <LayoutTemplate className="size-4 mr-1" />
          Send template
        </Button>

        {isEntity && useResponseText != null && useResponseText !== '' && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => onDraftChange(useResponseText)}
          >
            <FileText className="size-4 mr-1" />
            {useResponseLabel}
          </Button>
        )}

        {isEntity && onGetViewLink && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={viewLinkLoading}
            onClick={async () => {
              setViewLinkLoading(true);
              try {
                const url = await onGetViewLink();
                if (url) {
                  setReplyText((prev) => (prev.trim() ? `${prev.trim()}\n\n${url}` : url));
                }
              } finally {
                setViewLinkLoading(false);
              }
            }}
          >
            <Link2 className="size-4 mr-1" />
            {viewLinkLoading ? 'Getting link…' : 'Attach view link'}
          </Button>
        )}
      </div>

      <SendTemplateDialog
        entityType={entityType}
        entityId={entityId}
        contactId={entityId}
        open={templateDialogOpen}
        onOpenChange={setTemplateDialogOpen}
        onSent={() => {
          setTemplateDialogOpen(false);
          onSent?.();
        }}
      />
    </div>
  );
}
