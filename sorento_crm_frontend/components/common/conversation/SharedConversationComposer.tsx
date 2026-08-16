'use client';

import { useState, useRef, useEffect, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { toast } from 'sonner';
import {
  Send,
  Link2,
  LayoutTemplate,
  FileText,
  Info,
  Paperclip,
  Sparkles,
  StickyNote,
  X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Skeleton } from '@/components/ui/skeleton';
import SendTemplateDialog from '@/components/common/whatsapp-template/SendTemplateDialog';
import AttachmentPreviewModal, {
  type AttachmentPreviewItem,
} from '@/components/common/AttachmentPreviewModal';
import { useMessageSnippetOptions } from '@/app/(protected)/sla-management/message-snippets/hooks/useMessageSnippets';
import type { MessageSnippetOption } from '@/app/(protected)/sla-management/message-snippets/types/messageSnippet.types';
import { useConversationWindowState } from './useConversationWindowState';
import EmojiPickerButton from './EmojiPickerButton';
import SnippetPicker, { activeSlashFragment, filterSnippets } from './SnippetPicker';
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
   * Overrides the default send. Used where the send must be stamped with more
   * than (entityType, entityId) - e.g. an intervention ticket carrying files.
   */
  sendAdapter?: (payload: {
    text: string;
    files: File[];
  }) => Promise<{
    sent_as: 'text' | 'template' | 'attachment';
    /**
     * Per-file outcome of a multi-attachment send. The backend delivers files
     * in order and stops at the first failure, so `delivered` is the ordered
     * prefix the contact actually received.
     */
    attachments?: {
      delivered: string[];
      failed: { filename: string; error: string } | null;
    } | null;
  }>;
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
  /**
   * Overrides the manual template send, for surfaces whose template route is
   * not the entity chat one (the Conversations inbox is keyed by contact, and
   * its send derives the ticket rather than being given one).
   */
  templateSendAdapter?: (input: {
    template_id: string;
    params: Record<string, string>;
  }) => Promise<unknown>;
  /**
   * Offer the "/" snippet picker (UAC AC-L4). Off by default so the existing
   * entity chat panels are untouched; the intervention-ticket drawer turns it
   * on and supplies the ticket the `$variables` resolve against.
   */
  snippetsEnabled?: boolean;
  snippetTrackingId?: string | null;
  /** Offer the emoji picker (UAC AC-L5). */
  emojiEnabled?: boolean;
  /**
   * AI assist (UAC AC-L5): drafts a reply INTO this input. Resolves with the
   * draft text; rejects with an Error whose message is toasted. Anything
   * already typed is passed as the instruction, so "offer Tuesday delivery"
   * steers the draft instead of being lost. Absent = no button.
   */
  onAiAssist?: (input: { instruction?: string }) => Promise<string>;
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
  sendAdapter,
  windowStateOverride = null,
  showTemplateButton = true,
  templateSendTrackingId = null,
  templateSendAdapter,
  snippetsEnabled = false,
  snippetTrackingId = null,
  emojiEnabled = false,
  onAiAssist,
}: SharedConversationComposerProps) {
  const [replyText, setReplyText] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [sending, setSending] = useState(false);
  const [viewLinkLoading, setViewLinkLoading] = useState(false);
  const [templateDialogOpen, setTemplateDialogOpen] = useState(false);
  const [sendError, setSendError] = useState<{ message: string; settingsUrl: string } | null>(null);
  /** The staged file the last send could not deliver (marked on its chip). */
  const [failedFileName, setFailedFileName] = useState<string | null>(null);
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

  // ---- Snippets, emoji, AI assist (UAC AC-L4 / AC-L5) ---------------------

  // The "/..." fragment being typed, or null when the picker is closed. Opened
  // by the button too, with an empty query.
  const [slashFragment, setSlashFragment] = useState<{ start: number; query: string } | null>(
    null,
  );
  // The same picker, opened from the toolbar button instead of a "/". Kept
  // apart from the fragment because a button-opened pick inserts at the caret
  // rather than replacing a typed "/query".
  const [snippetMenuOpen, setSnippetMenuOpen] = useState(false);
  const [snippetIndex, setSnippetIndex] = useState(0);
  const [aiDrafting, setAiDrafting] = useState(false);

  const snippetPickerOpen = snippetsEnabled && (slashFragment !== null || snippetMenuOpen);
  const snippetsQuery = useMessageSnippetOptions(snippetTrackingId, snippetPickerOpen);
  const snippetMatches = useMemo(
    () => filterSnippets(snippetsQuery.data ?? [], slashFragment?.query ?? ''),
    [snippetsQuery.data, slashFragment],
  );

  const closeSnippetPicker = () => {
    setSlashFragment(null);
    setSnippetMenuOpen(false);
  };

  useEffect(() => {
    setSnippetIndex(0);
  }, [slashFragment?.query]);

  // A different conversation is a different draft: never leave a picker open
  // over someone else's thread.
  useEffect(() => {
    setSlashFragment(null);
    setSnippetMenuOpen(false);
  }, [entityId]);

  /** Write `text` where the caret is, and leave the caret after it. */
  const insertAtCaret = (text: string) => {
    const node = replyTextareaRef.current;
    const start = node?.selectionStart ?? replyText.length;
    const end = node?.selectionEnd ?? start;
    const next = replyText.slice(0, start) + text + replyText.slice(end);
    setReplyText(next);
    if (sendError) setSendError(null);
    const caret = start + text.length;
    queueMicrotask(() => {
      node?.focus();
      node?.setSelectionRange?.(caret, caret);
    });
  };

  /**
   * Insert the snippet, replacing the "/query" that summoned it. The body is
   * ALREADY resolved by the backend, and it stays editable afterwards - it is
   * just text in the box now.
   */
  const insertSnippet = (snippet: MessageSnippetOption) => {
    const fragment = slashFragment;
    closeSnippetPicker();
    const body = snippet.resolved_body || snippet.body;
    if (!fragment) {
      insertAtCaret(body);
      return;
    }
    const node = replyTextareaRef.current;
    const caret = node?.selectionStart ?? fragment.start + fragment.query.length + 1;
    const next = replyText.slice(0, fragment.start) + body + replyText.slice(caret);
    setReplyText(next);
    if (sendError) setSendError(null);
    const nextCaret = fragment.start + body.length;
    queueMicrotask(() => {
      node?.focus();
      node?.setSelectionRange?.(nextCaret, nextCaret);
    });
  };

  const runAiAssist = async () => {
    if (!onAiAssist || aiDrafting) return;
    const instruction = replyText.trim();
    setAiDrafting(true);
    try {
      const draft = await onAiAssist(instruction ? { instruction } : {});
      const text = (draft ?? '').trim();
      if (!text) {
        toast.error('The assistant returned an empty draft.');
        return;
      }
      // The draft lands UNDER whatever was already typed, separated by a blank
      // line. That text steered the draft, but it is the author's - deleting it
      // to make room is not ours to do, and they can cut it in one gesture.
      setReplyText(instruction ? `${instruction}\n\n${text}` : text);
      if (sendError) setSendError(null);
      queueMicrotask(() => replyTextareaRef.current?.focus());
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to draft a reply');
    } finally {
      setAiDrafting(false);
    }
  };

  const onDraftChange = (value: string) => {
    setReplyText(value);
    if (sendError) setSendError(null);
  };

  /** Typing handler for the message field: also drives the "/" picker. */
  const onComposerInput = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = event.target.value;
    onDraftChange(value);
    if (!snippetsEnabled) return;
    // A picker opened from the BUTTON has no "/query" to track, so nothing ever
    // closed it: it stayed over the box while a message was written, and Enter
    // inserted a snippet instead of sending. Typing dismisses it; a "/" at the
    // start of the input re-opens it through the fragment below.
    if (snippetMenuOpen) setSnippetMenuOpen(false);
    setSlashFragment(
      activeSlashFragment(value, event.target.selectionStart ?? value.length),
    );
  };

  /** Arrow/Enter/Escape while the picker is open belong to the picker. */
  const onSnippetKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>): boolean => {
    if (!snippetPickerOpen) return false;
    if (event.key === 'Escape') {
      event.preventDefault();
      closeSnippetPicker();
      return true;
    }
    if (snippetMatches.length === 0) return false;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setSnippetIndex((i) => (i + 1) % snippetMatches.length);
      return true;
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      setSnippetIndex((i) => (i - 1 + snippetMatches.length) % snippetMatches.length);
      return true;
    }
    if (event.key === 'Enter' || event.key === 'Tab') {
      event.preventDefault();
      insertSnippet(snippetMatches[snippetIndex]);
      return true;
    }
    return false;
  };

  // ---- Staged image previews -------------------------------------------
  // A pasted screenshot is unrecognisable as a filename ("image.png"), so the
  // staged strip shows the picture itself. A staged file has no URL of its own,
  // so each image gets an object URL, revoked as soon as the list changes or
  // the composer unmounts - the cleanup runs on the PREVIOUS array, which is
  // exactly the set that just stopped being displayed.
  const stagedImageUrls = useMemo(
    () =>
      files.map((file) =>
        file.type.startsWith('image/') && typeof URL?.createObjectURL === 'function'
          ? URL.createObjectURL(file)
          : null,
      ),
    [files],
  );
  useEffect(
    () => () => {
      stagedImageUrls.forEach((url) => url && URL.revokeObjectURL?.(url));
    },
    [stagedImageUrls],
  );
  /** Which staged file the preview is open on (index into `files`), or null. */
  const [previewFileIndex, setPreviewFileIndex] = useState<number | null>(null);
  const stagedPreviewItems = useMemo(() => {
    const out: { fileIndex: number; item: AttachmentPreviewItem }[] = [];
    files.forEach((file, index) => {
      const url = stagedImageUrls[index];
      if (!url) return;
      out.push({ fileIndex: index, item: { id: `staged-${index}`, name: file.name, url } });
    });
    return out;
  }, [files, stagedImageUrls]);
  const previewStartIndex = Math.max(
    0,
    stagedPreviewItems.findIndex((entry) => entry.fileIndex === previewFileIndex),
  );

  const canSubmit = !!replyText.trim() || (attachmentsEnabled && files.length > 0);

  const handleSend = async () => {
    const typed = replyText.trim();
    if (!canSubmit || sending || !canReply) return;
    // The exact files this send is carrying: the per-file outcome below is
    // positional (the backend delivers in order and stops at the first
    // failure), so it must be matched against THIS list, not later state.
    const sentFiles = files;
    const text = typed;
    setSending(true);
    setSendError(null);
    setFailedFileName(null);
    try {
      const result = sendAdapter
        ? await sendAdapter({ text, files: sentFiles })
        : await sendConversationMessage(entityType, entityId, text);
      // Partial delivery: the text and the delivered files are gone for good
      // (the contact has them), so only what did NOT reach them stays staged -
      // otherwise a retry sends the same photo to the customer twice.
      const failed = 'attachments' in result ? (result.attachments?.failed ?? null) : null;
      const deliveredCount =
        'attachments' in result ? (result.attachments?.delivered?.length ?? 0) : 0;
      // Staged files but nothing reported delivered and nothing reported failed:
      // the send silently degraded to text-only somewhere in the chain, and the
      // contact never got the file. Treat it as a failure - clearing the chips
      // here is what made the backend's multipart parsing bug invisible for so
      // long. The text itself did go out, so only the files stay staged.
      const attachmentsDropped = sentFiles.length > 0 && !failed && deliveredCount === 0;
      setReplyText('');
      setFiles(failed ? sentFiles.slice(deliveredCount) : attachmentsDropped ? sentFiles : []);
      setFailedFileName(failed?.filename ?? null);
      if (attachmentsDropped) {
        toast.error(
          sentFiles.length === 1
            ? `${sentFiles[0].name} was not sent. Try again.`
            : 'The attachments were not sent. Try again.',
        );
      } else if (failed) {
        toast.error(`${failed.filename} was not sent: ${failed.error}`);
      } else if (!sendAdapter) {
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

  const addFiles = (picked: FileList | File[] | null | undefined) => {
    if (sending) return;
    if (!picked?.length) return;
    setFiles((prev) => [...prev, ...Array.from(picked)]);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  /**
   * Pasting into the message box (Cmd/Ctrl+V) stages whatever files the
   * clipboard carries - a screenshot, a copied file - through the SAME path as
   * the Attach button, which is what makes it behave like WhatsApp / Respond.
   * Text pastes are untouched: the handler only intervenes when there are files.
   */
  const handlePaste = (event: React.ClipboardEvent<HTMLTextAreaElement>) => {
    if (!attachmentsEnabled || sending) return;
    const pasted = Array.from(event.clipboardData?.files ?? []);
    if (pasted.length === 0) return;
    event.preventDefault();
    addFiles(pasted);
  };

  const removeStagedFile = (idx: number, notSent: boolean) => {
    if (sending) return;
    if (notSent) setFailedFileName(null);
    setPreviewFileIndex(null);
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  };

  const attachmentChips =
    attachmentsEnabled && files.length > 0 ? (
      <div className="flex flex-wrap items-start gap-1.5" data-testid="composer-attachments">
        {files.map((file, idx) => {
          const notSent = failedFileName === file.name;
          const thumbUrl = stagedImageUrls[idx];
          if (thumbUrl) {
            // An image stages as a thumbnail; clicking it opens the SAME
            // preview surface the thread bubbles use.
            return (
              <span
                key={`${file.name}-${idx}`}
                data-testid={notSent ? 'composer-attachment-failed' : 'composer-attachment'}
                className={`relative inline-block size-14 overflow-hidden rounded-md border${
                  notSent ? ' border-destructive' : ''
                }`}
                title={notSent ? `${file.name} - not sent` : file.name}
              >
                <button
                  type="button"
                  className="block size-full"
                  aria-label={`Preview ${file.name}`}
                  onClick={() => setPreviewFileIndex(idx)}
                >
                  {/* A local object URL: next/image needs configured hosts. */}
                  <img src={thumbUrl} alt={file.name} className="size-full object-cover" />
                  <span className="sr-only">{file.name}</span>
                </button>
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  className="absolute end-0 top-0 size-5 rounded-none bg-background/80"
                  aria-label={`Remove ${file.name}`}
                  disabled={sending}
                  onClick={() => removeStagedFile(idx, notSent)}
                >
                  <X className="size-3" />
                </Button>
              </span>
            );
          }
          return (
            <span
              key={`${file.name}-${idx}`}
              data-testid={notSent ? 'composer-attachment-failed' : 'composer-attachment'}
              className={`inline-flex max-w-full items-center gap-1 rounded-full border px-2 py-0.5 text-xs${
                notSent ? ' border-destructive text-destructive' : ''
              }`}
              title={notSent ? `${file.name} - not sent` : file.name}
            >
              <Paperclip className="size-3 shrink-0" />
              <span className="truncate">{file.name}</span>
              <Button
                type="button"
                size="icon"
                variant="ghost"
                className="size-4 shrink-0"
                aria-label={`Remove ${file.name}`}
                // Frozen while a send is in flight: the per-file outcome is
                // positional against the list THIS send carried, so a removal
                // accepted mid-flight is undone by the partial re-stage below
                // and the file goes to the contact on the next Send.
                disabled={sending}
                onClick={() => removeStagedFile(idx, notSent)}
              >
                <X className="size-3" />
              </Button>
            </span>
          );
        })}
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
            onChange={onComposerInput}
            onPaste={handlePaste}
            onKeyDown={(e) => onSnippetKeyDown(e)}
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
      {attachmentChips}

      {/* The message field and its typeaheads share one positioning context, so
          the "/" picker floats above whichever field mode is rendered. */}
      <div className="relative">
        {snippetPickerOpen && (
          <SnippetPicker
            items={snippetMatches}
            isLoading={snippetsQuery.isLoading}
            error={
              snippetsQuery.isError
                ? snippetsQuery.error instanceof Error
                  ? snippetsQuery.error.message
                  : 'Failed to load snippets'
                : null
            }
            activeIndex={snippetIndex}
            onActiveIndexChange={setSnippetIndex}
            onPick={insertSnippet}
          />
        )}

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
            onChange={onComposerInput}
            onPaste={handlePaste}
            onKeyDown={(e) => {
              // The picker owns the arrows and Enter while it is open, or
              // choosing a snippet would send an unfinished message instead.
              if (onSnippetKeyDown(e)) return;
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
      </div>

      {/* Send-time no_chat_template fallback (rare race after preview said OK). */}
      {sendError && noTemplateNotice(sendError.settingsUrl, sendError.message)}

      <div className="flex flex-wrap gap-2">
        {attachButton}

        {snippetsEnabled && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={sending}
            aria-label="Insert snippet"
            data-testid="snippet-button"
            onClick={() => {
              if (snippetPickerOpen) {
                closeSnippetPicker();
                return;
              }
              setSlashFragment(null);
              setSnippetMenuOpen(true);
            }}
          >
            <StickyNote className="size-4 mr-1" />
            Snippet
          </Button>
        )}

        {emojiEnabled && (
          <EmojiPickerButton disabled={sending} onSelect={(emoji) => insertAtCaret(emoji)} />
        )}

        {onAiAssist && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={sending || aiDrafting}
            data-testid="ai-assist-button"
            title="Draft a reply from this conversation"
            onClick={() => void runAiAssist()}
          >
            <Sparkles className={`size-4 mr-1${aiDrafting ? ' animate-pulse' : ''}`} />
            {aiDrafting ? 'Drafting…' : 'AI assist'}
          </Button>
        )}

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

      {/* Staged images open the SAME preview surface the thread bubbles use -
          no second lightbox. The item's url IS the local object URL, so no
          byte-fetch is needed and none is passed. */}
      <AttachmentPreviewModal
        open={previewFileIndex !== null && stagedPreviewItems.length > 0}
        onOpenChange={(next) => {
          if (!next) setPreviewFileIndex(null);
        }}
        items={stagedPreviewItems.map((entry) => entry.item)}
        startIndex={previewStartIndex}
      />

      <SendTemplateDialog
        entityType={entityType}
        entityId={entityId}
        contactId={entityId}
        trackingId={templateSendTrackingId}
        sendAdapter={templateSendAdapter}
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
