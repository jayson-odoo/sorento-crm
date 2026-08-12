'use client';

import { useState, useRef, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { toast } from 'sonner';
import { Send, Link2, LayoutTemplate, FileText, Info, Paperclip, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Skeleton } from '@/components/ui/skeleton';
import SendTemplateDialog from '@/components/common/whatsapp-template/SendTemplateDialog';
import { buildQuotedReplyText } from '@/lib/respondIoChatRender';
import { useConversationWindowState } from './useConversationWindowState';
import {
  sendConversationMessage,
  getChatTemplatePreview,
  NoChatTemplateError,
  type ChatTemplatePreview,
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
  /**
   * Offer file attachments (image / video / audio / document). Off by default so
   * existing surfaces are unchanged; the intervention-ticket drawer turns it on.
   * Respond.io has no sticker type, so there is deliberately no sticker option.
   */
  attachmentsEnabled?: boolean;
  /**
   * Message being replied to. Respond.io has no reply-to parameter, so the
   * excerpt is carried as a ">" quote prefix on the outgoing text.
   */
  replyTo?: { messageId: string | number | null; excerpt: string } | null;
  onClearReplyTo?: () => void;
  /**
   * Overrides the default send. Used where the send must be stamped with more
   * than (entityType, entityId) - e.g. an intervention ticket carrying files and
   * a quoted message.
   */
  sendAdapter?: (payload: {
    text: string;
    files: File[];
    replyToMessageId?: string | number | null;
    replyToExcerpt?: string | null;
  }) => Promise<{ sent_as: 'text' | 'template' | 'attachment' }>;
  /**
   * Supplies the 24h window + out-of-window template instead of the composer
   * fetching them, for callers that already loaded them with the record.
   */
  windowStateOverride?: { closed: boolean; template?: ChatTemplatePreview | null } | null;
  /** Hide the "Send template" button (surfaces that resolve templates elsewhere). */
  showTemplateButton?: boolean;
  /**
   * Intervention ticket the manual "Send template" dialog answers. Without it a
   * template send is a reply the ticket never hears about, so the response clock
   * keeps running and the ticket breaches while visibly answered.
   */
  templateSendTrackingId?: string | null;
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
  attachmentsEnabled = false,
  replyTo = null,
  onClearReplyTo,
  sendAdapter,
  windowStateOverride = null,
  showTemplateButton = true,
  templateSendTrackingId = null,
}: SharedConversationComposerProps) {
  const [replyText, setReplyText] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [sending, setSending] = useState(false);
  const [viewLinkLoading, setViewLinkLoading] = useState(false);
  const [templateDialogOpen, setTemplateDialogOpen] = useState(false);
  const [sendError, setSendError] = useState<{ message: string; settingsUrl: string } | null>(null);
  const replyTextareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const appliedPrefillKeyRef = useRef(0);

  const { windowClosed: fetchedWindowClosed } = useConversationWindowState(
    entityType,
    entityId,
    canReply && !windowStateOverride,
  );
  const windowClosed = windowStateOverride ? windowStateOverride.closed : fetchedWindowClosed;
  const isEntity = mode === 'entity';

  // Out-of-window: fetch the form's chat template so we can render it inline with
  // a fill-in field. DB-only on the backend — no Respond call.
  const { data: fetchedPreview, isLoading: previewLoading } = useQuery({
    queryKey: ['chat-template-preview', entityType, entityId],
    queryFn: () => getChatTemplatePreview(entityType, entityId),
    enabled: canReply && windowClosed && !windowStateOverride,
    staleTime: 60_000,
  });
  const preview = windowStateOverride
    ? (windowStateOverride.template ?? { configured: false })
    : fetchedPreview;

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

  const canSubmit = !!replyText.trim() || (attachmentsEnabled && files.length > 0);

  const handleSend = async () => {
    const typed = replyText.trim();
    if (!canSubmit || sending || !canReply) return;
    // Respond.io carries no reply-to reference, so a quoted reply ships as a
    // ">" prefixed excerpt above the body (rendered as a quote by WhatsApp and
    // by our own chat list).
    const text = replyTo?.excerpt ? buildQuotedReplyText(replyTo.excerpt, typed) : typed;
    setSending(true);
    setSendError(null);
    try {
      const result = sendAdapter
        ? await sendAdapter({
            text,
            files,
            replyToMessageId: replyTo?.messageId ?? null,
            replyToExcerpt: replyTo?.excerpt ?? null,
          })
        : await sendConversationMessage(entityType, entityId, text);
      setReplyText('');
      setFiles([]);
      onClearReplyTo?.();
      if (!sendAdapter) {
        // The adapter owns its own success feedback (it knows what it sent).
        toast.success(
          result.sent_as === 'template' ? 'Delivered as a template message' : 'Message sent',
        );
      }
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
      disabled={!canSubmit || sending}
      onClick={handleSend}
      aria-label="Send"
    >
      <Send className="size-4" />
    </Button>
  );

  const addFiles = (picked: FileList | null) => {
    if (!picked?.length) return;
    setFiles((prev) => [...prev, ...Array.from(picked)]);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  // Quoted message being replied to (Respond has no reply-to field; see handleSend).
  const replyToChip = replyTo ? (
    <div
      className="flex items-start gap-2 rounded-md border-s-2 border-primary bg-muted/40 px-2.5 py-1.5 text-xs"
      data-testid="composer-reply-to"
    >
      <span className="line-clamp-2 flex-1 italic text-muted-foreground">{replyTo.excerpt}</span>
      {onClearReplyTo && (
        <Button
          type="button"
          size="icon"
          variant="ghost"
          className="size-5 shrink-0"
          aria-label="Cancel reply"
          onClick={onClearReplyTo}
        >
          <X className="size-3.5" />
        </Button>
      )}
    </div>
  ) : null;

  const attachmentChips =
    attachmentsEnabled && files.length > 0 ? (
      <div className="flex flex-wrap gap-1.5" data-testid="composer-attachments">
        {files.map((file, idx) => (
          <span
            key={`${file.name}-${idx}`}
            className="inline-flex max-w-full items-center gap-1 rounded-full border px-2 py-0.5 text-xs"
            title={file.name}
          >
            <Paperclip className="size-3 shrink-0" />
            <span className="truncate">{file.name}</span>
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="size-4 shrink-0"
              aria-label={`Remove ${file.name}`}
              onClick={() => setFiles((prev) => prev.filter((_, i) => i !== idx))}
            >
              <X className="size-3" />
            </Button>
          </span>
        ))}
      </div>
    ) : null;

  const attachButton = attachmentsEnabled ? (
    <>
      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        data-testid="composer-file-input"
        onChange={(e) => addFiles(e.target.files)}
      />
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={sending}
        onClick={() => fileInputRef.current?.click()}
      >
        <Paperclip className="size-4 mr-1" />
        Attach
      </Button>
    </>
  ) : null;

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
      {replyToChip}
      {attachmentChips}

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
        {attachButton}

        {showTemplateButton && (
          <Button
            type="button"
            variant={windowClosed ? 'primary' : 'outline'}
            size="sm"
            onClick={() => setTemplateDialogOpen(true)}
          >
            <LayoutTemplate className="size-4 mr-1" />
            Send template
          </Button>
        )}

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
        trackingId={templateSendTrackingId}
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
