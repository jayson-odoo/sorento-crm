'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { CornerUpLeft, Loader2, Mic, Paperclip, RotateCcw, SendHorizonal, Trash2, X } from 'lucide-react';
import { TurnAttachments } from '@/components/chatbot/TurnAttachments';
import AttachmentPreviewModal from '@/components/common/AttachmentPreviewModal';
import MessageBubbleActions from '@/components/common/conversation/MessageBubbleActions';
import { WhatsAppText } from '@/components/chatbot/WhatsAppText';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import { formatElapsed, useVoiceRecorder } from '@/components/common/conversation/useVoiceRecorder';
import { toast } from '@/lib/toast';
import { cn } from '@/lib/utils';
import { getRespondContactsOutbound } from '../../respond-contacts/services/respondContactOutboundService';
import { useChatbotConsole } from '../hooks/useChatbotConsole';
import type { ChatbotConsoleMessage, ConsoleMediaInput, ConsoleQuote } from '../types/chatbotConsole.types';

/** A press on the mic shorter than this is a tap (recording keeps going, with a bar to
 * send or delete it); longer is WhatsApp's hold, where letting go sends. */
const VOICE_HOLD_MS = 350;
/** How far a held press slides left before it discards the clip. */
const VOICE_SLIDE_CANCEL_PX = 80;

export const CHATBOT_CONSOLE_VIEW_PERMISSION = 'system.chat_history.view';

async function fetchContactOptions(query: string): Promise<SearchableSelectOption[]> {
  const result = await getRespondContactsOutbound({ pageIndex: 0, pageSize: 20, searchQuery: query });
  return result.data
    .filter((row) => Boolean(row.respond_io_id))
    .map((row) => ({
      value: row.respond_io_id as string,
      label: row.name || row.phone_number || (row.respond_io_id as string),
      description: row.name && row.phone_number ? row.phone_number : undefined,
    }));
}

/** "v18 · full · production": version, lineage, label when any - never a UUID. */
function promptVersionLabel(version: { version: number; label: string | null; base: string }): string {
  return [`v${version.version}`, version.base, version.label].filter(Boolean).join(' \u00b7 ');
}

function MediaPreview({ message }: { message: ChatbotConsoleMessage }) {
  if (!message.mediaKind || !message.mediaUrl) return null;
  if (message.mediaKind === 'image') {
    return (
      <a href={message.mediaUrl} target="_blank" rel="noreferrer noopener" className="mb-1.5 block">
        {/* A local blob: URL, not a remote one - next/image cannot optimise it, so a
            plain img is correct here rather than a config exception. */}
        <img src={message.mediaUrl} alt="Attached" className="max-h-48 rounded-lg object-cover" />
      </a>
    );
  }
  return (
    <audio controls src={message.mediaUrl} className="mb-1.5 h-9 max-w-full">
      Your browser cannot play this audio.
    </audio>
  );
}

function MessageBubble({
  message,
  onQuickReply,
  onRetryMedia,
  onReply,
}: {
  message: ChatbotConsoleMessage;
  onQuickReply: (text: string) => void;
  onRetryMedia: (media: ConsoleMediaInput, quote: ConsoleQuote | null) => void;
  /** Absent = nothing the backend can quote (greeting, status line, unacknowledged send). */
  onReply?: () => void;
}) {
  const isUser = message.role === 'user';
  const isMediaPending = message.mediaStatus === 'pending';
  return (
    <div className={cn('flex', isUser ? 'justify-end' : 'justify-start')}>
      <MessageBubbleActions
        enabled
        onReply={onReply}
        copyText={message.text}
        className={cn(
          'max-w-[85%] rounded-2xl px-3 py-2.5 text-sm leading-relaxed shadow-sm',
          isUser ? 'bg-primary/15 text-foreground' : 'bg-muted text-foreground',
        )}
      >
        {isUser && message.quotedText ? (
          <p className="mb-1 line-clamp-3 break-words border-l-2 border-border pl-2 text-xs text-muted-foreground">
            {message.quotedText}
          </p>
        ) : null}
        <MediaPreview message={message} />
        <p
          className={cn(
            'whitespace-pre-wrap break-words',
            !isUser && (isMediaPending || message.mediaStatus) && 'italic text-muted-foreground',
          )}
        >
          {isMediaPending ? <Loader2 className="mr-1 inline size-3.5 animate-spin" /> : null}
          {isUser ? message.text : <WhatsAppText text={message.text} />}
        </p>
        {message.attachments && message.attachments.length > 0 ? (
          <TurnAttachments attachments={message.attachments} />
        ) : null}
        {message.mediaStatus === 'failed' && message.mediaRetry ? (
          <div className="mt-1.5">
            <button
              type="button"
              onClick={() => onRetryMedia(message.mediaRetry as ConsoleMediaInput, message.mediaRetryQuote ?? null)}
              className="rounded-full border bg-secondary px-3 py-1 text-xs hover:bg-secondary/80"
            >
              Retry
            </button>
          </div>
        ) : null}
        {message.branchKind || (!isUser && message.promptVersion != null) ? (
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            {message.branchKind ? (
              <Badge variant="secondary" size="sm">
                {message.branchKind}
              </Badge>
            ) : null}
            {!isUser && message.promptVersion != null ? (
              <span
                className="rounded-full border border-border/60 px-1.5 py-0.5 text-2xs leading-none text-muted-foreground"
                title="Parser prompt version this reply ran"
                data-testid="chatbot-console-prompt-pill"
              >
                v{message.promptVersion}
              </span>
            ) : null}
            {message.turnId ? (
              <Link
                href={`/system-management/chat-history?turn=${encodeURIComponent(message.turnId)}`}
                target="_blank"
                rel="noreferrer noopener"
                className="text-xs text-muted-foreground underline underline-offset-2 hover:text-primary"
              >
                trace
              </Link>
            ) : null}
          </div>
        ) : null}
        {!isUser && message.routingLine ? (
          <p
            className="mt-1 break-words text-xs text-muted-foreground"
            data-testid="chatbot-console-routing-line"
          >
            {message.routingLine}
          </p>
        ) : null}
        {message.quickReplies && message.quickReplies.length > 0 ? (
          <div className="mt-2 flex flex-wrap gap-2">
            {message.quickReplies.map((chip, index) => (
              <button
                key={`${index}-${chip}`}
                type="button"
                onClick={() => onQuickReply(chip)}
                className="rounded-full border bg-secondary px-3 py-1 text-xs hover:bg-secondary/80"
                title={chip}
              >
                {chip}
              </button>
            ))}
          </div>
        ) : null}
      </MessageBubbleActions>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex justify-start" data-testid="chatbot-console-typing">
      <div className="rounded-2xl bg-muted px-3 py-2.5 shadow-sm">
        <div className="flex items-center gap-1">
          <span className="size-2 animate-bounce rounded-full bg-muted-foreground/70 [animation-delay:-0.3s]" />
          <span className="size-2 animate-bounce rounded-full bg-muted-foreground/70 [animation-delay:-0.15s]" />
          <span className="size-2 animate-bounce rounded-full bg-muted-foreground/70" />
        </div>
      </div>
    </div>
  );
}

export default function ChatbotConsole() {
  const {
    contactId,
    contactLabel,
    setContact,
    promptVersionId,
    setPromptVersionId,
    promptVersions,
    promptVersionsLoading,
    messages,
    sending,
    sendText,
    sendQuickReply,
    sendMedia,
    retryMedia,
    reset,
    runId,
  } = useChatbotConsole();

  const [draft, setDraft] = useState('');
  const [replyToId, setReplyToId] = useState('');
  // One image (or audio file) waiting for Send: the console's media turn takes one file.
  const [staged, setStaged] = useState<File | null>(null);
  const [stagedUrl, setStagedUrl] = useState<string | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const threadEndRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // Minted in an effect, never in render, so a discarded render cannot leak the URL.
  useEffect(() => {
    if (!staged || typeof URL?.createObjectURL !== 'function') {
      setStagedUrl(null);
      return;
    }
    const url = URL.createObjectURL(staged);
    setStagedUrl(url);
    return () => URL.revokeObjectURL?.(url);
  }, [staged]);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, sending]);

  const promptVersionOptions = useMemo<SearchableSelectOption[]>(
    () =>
      promptVersions.map((version) => ({
        value: version.id,
        label: promptVersionLabel(version),
      })),
    [promptVersions],
  );

  // The version actually in effect, spelled out next to the composer - "Parser v38", never
  // the raw id. `promptVersionId === null` after the versions have loaded is an explicit
  // in-session pick of the live production label (the select's "clear" option), not a
  // loading state.
  const activePromptVersion = promptVersions.find((v) => v.id === promptVersionId);
  const activePromptLabel = promptVersionsLoading
    ? null
    : activePromptVersion
      ? `Parser v${activePromptVersion.version}`
      : promptVersions.length > 0
        ? 'Parser live (production)'
        : null;

  // The bubbles a message can quote: bot replies of a real turn and the customer's own sent messages
  // (never the greeting lines).
  const isQuotable = (m: ChatbotConsoleMessage) => (m.role === 'bot' ? Boolean(m.turnId) : Boolean(m.messageId));
  const quoted = messages.find((m) => m.id === replyToId && isQuotable(m));
  const quote: ConsoleQuote | null = quoted
    ? quoted.role === 'user'
      ? { id: quoted.messageId as string, text: quoted.text, source: 'contact' }
      : { id: quoted.id, text: quoted.text, source: 'n8n' }
    : null;

  const startReply = (id: string) => {
    setReplyToId(id);
    window.setTimeout(() => textareaRef.current?.focus(), 0);
  };

  const sendStaged = (file: File) => {
    if (!contactId) {
      toast.error('Pick a contact before sending a message.');
      return;
    }
    const caption = draft;
    setDraft('');
    setStaged(null);
    setPreviewOpen(false);
    setReplyToId('');
    void sendMedia(file.type.startsWith('audio/') ? 'audio' : 'image', file, caption, quote);
  };

  const handleSend = () => {
    if (sending) return;
    if (staged) {
      sendStaged(staged);
      return;
    }
    if (!draft.trim()) return;
    const text = draft;
    setDraft('');
    setReplyToId('');
    void sendText(text, quote);
  };

  /** Ctrl/Cmd+V (or a phone's Paste) with an image on the clipboard stages it; text pastes
   * are left to the browser. */
  const handlePaste = (event: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const image = Array.from(event.clipboardData?.files ?? []).find((f) => f.type.startsWith('image/'));
    if (!image) return;
    event.preventDefault();
    setStaged(image);
  };

  const voice = useVoiceRecorder({
    onClip: (file) => {
      const caption = draft;
      setDraft('');
      setReplyToId('');
      void sendMedia('audio', file, caption, quote);
    },
  });

  // ---- WhatsApp mic: tap = keep recording with a bar, hold = release sends, slide left
  // cancels. `press` is the live gesture; `voiceLocked` is the tap mode's bar.
  const press = useRef<{ id: number; x: number; at: number; started: boolean; released: boolean; cancelled: boolean } | null>(
    null,
  );
  const [holding, setHolding] = useState(false);
  const [voiceLocked, setVoiceLocked] = useState(false);
  useEffect(() => {
    if (!voice.recording) setVoiceLocked(false);
  }, [voice.recording]);

  const voiceUnavailableMessage = () =>
    typeof window !== 'undefined' && window.isSecureContext === false
      ? 'Voice recording needs a secure (https) page.'
      : (voice.reason ?? 'Voice recording is not supported in this browser.');

  const onMicPointerDown = async (event: React.PointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    if (sending || press.current) return;
    if (!voice.available) {
      toast.error(voiceUnavailableMessage());
      return;
    }
    try {
      event.currentTarget.setPointerCapture?.(event.pointerId);
    } catch {
      // No capture (old browser): a release off the button still arrives as pointercancel/up elsewhere.
    }
    const gesture = { id: event.pointerId, x: event.clientX, at: Date.now(), started: false, released: false, cancelled: false };
    press.current = gesture;
    setHolding(true);
    const problem = await voice.start();
    if (problem) {
      press.current = null;
      setHolding(false);
      setVoiceLocked(false);
      toast.error(
        /blocked/i.test(problem)
          ? `${problem} Allow the microphone in the browser's site settings, then try again.`
          : problem,
      );
      return;
    }
    gesture.started = true;
    if (gesture.cancelled) {
      voice.cancel();
      press.current = null;
    } else if (gesture.released) {
      // Let go before the recorder was ready (a tap, or a permission prompt): keep recording.
      setVoiceLocked(true);
      press.current = null;
    }
  };

  const onMicPointerMove = (event: React.PointerEvent<HTMLButtonElement>) => {
    const g = press.current;
    if (!g || g.released || event.pointerId !== g.id) return;
    if (g.x - event.clientX > VOICE_SLIDE_CANCEL_PX) {
      g.cancelled = true;
      g.released = true;
      setHolding(false);
      if (g.started) {
        voice.cancel();
        press.current = null;
      }
    }
  };

  const onMicPointerUp = (event: React.PointerEvent<HTMLButtonElement>) => {
    const g = press.current;
    if (!g || g.released || event.pointerId !== g.id) return;
    g.released = true;
    setHolding(false);
    if (!g.started) return; // onMicPointerDown decides once the recorder is ready
    press.current = null;
    if (Date.now() - g.at >= VOICE_HOLD_MS) voice.stop();
    else setVoiceLocked(true);
  };

  // The browser took the gesture (a scroll, a call): keep the clip, the bar can send or delete it.
  const onMicPointerCancel = (event: React.PointerEvent<HTMLButtonElement>) => {
    const g = press.current;
    if (!g || g.released || event.pointerId !== g.id) return;
    g.released = true;
    setHolding(false);
    if (g.started) {
      press.current = null;
      setVoiceLocked(true);
    }
  };

  // Reset or another contact is a new thread: no quote, staged file or open mic carries over.
  const voiceCancelRef = useRef(voice.cancel);
  voiceCancelRef.current = voice.cancel;
  useEffect(() => {
    voiceCancelRef.current();
    press.current = null;
    setHolding(false);
    setReplyToId('');
    setStaged(null);
  }, [runId]);

  const recordingBar = voice.recording ? (
    <div
      data-testid="chatbot-console-recording"
      className="flex h-10 min-w-0 flex-1 items-center gap-2 rounded-md border border-destructive/50 px-3"
    >
      <span className="size-2 shrink-0 animate-pulse rounded-full bg-destructive" />
      <span className="text-sm tabular-nums">{formatElapsed(voice.seconds)}</span>
      {!voiceLocked ? (
        <span className="ms-auto truncate text-xs text-muted-foreground">{'\u2039'} Slide to cancel</span>
      ) : null}
    </div>
  ) : null;

  const quotedLabel = quoted ? (quoted.role === 'user' ? contactLabel || 'Contact' : 'Chatbot') : '';

  return (
    <div
      className="flex min-h-[70dvh] flex-col gap-3 lg:h-[calc(100dvh-13rem)]"
      data-testid="chatbot-console"
    >
      {/* Header row: contact, prompt version, reset. */}
      <div className="flex flex-wrap items-end gap-3 border-b pb-3">
        <div className="min-w-[220px] flex-1 sm:flex-none">
          <Label className="mb-1 block text-xs text-muted-foreground">Contact</Label>
          <SearchableSelect
            value={contactId ?? ''}
            onChange={() => {
              /* handled via onOptionChange, which also carries the label */
            }}
            onOptionChange={(option) => {
              if (option) setContact(option.value, option.label);
            }}
            fetchOptions={fetchContactOptions}
            selectedOption={contactId ? { value: contactId, label: contactLabel } : undefined}
            placeholder="Pick a contact..."
            size="sm"
          />
        </div>
        <div className="min-w-[220px] flex-1 sm:flex-none">
          <Label className="mb-1 block text-xs text-muted-foreground">Prompt version</Label>
          <SearchableSelect
            value={promptVersionId ?? ''}
            onChange={(value) => setPromptVersionId(value || null)}
            options={promptVersionOptions}
            clearable
            placeholder="Live (production label)"
            size="sm"
          />
        </div>
        <Button type="button" variant="outline" size="sm" onClick={reset} className="gap-1.5">
          <RotateCcw className="size-3.5" />
          Reset
        </Button>
      </div>

      {/* Thread - the ONLY scrolling region. x is clipped so a swiped bubble never scrolls it sideways. */}
      <div
        className="min-h-0 flex-1 space-y-3 overflow-y-auto overflow-x-hidden pr-1"
        data-testid="chatbot-console-thread"
      >
        {messages.map((message) => (
          <MessageBubble
            key={message.id}
            message={message}
            onQuickReply={sendQuickReply}
            onRetryMedia={retryMedia}
            onReply={isQuotable(message) ? () => startReply(message.id) : undefined}
          />
        ))}
        {sending ? <TypingIndicator /> : null}
        <div ref={threadEndRef} />
      </div>

      {/* Composer - pinned at the bottom. */}
      <div className="space-y-2 border-t pt-3">
        {activePromptLabel ? (
          <div
            className="text-2xs text-muted-foreground"
            title="The parser prompt version this turn will run"
            data-testid="chatbot-console-active-prompt"
          >
            {activePromptLabel}
          </div>
        ) : null}
        {quoted ? (
          <div
            data-testid="chatbot-console-reply-to"
            className="flex items-start gap-2 rounded-md border-s-4 border-emerald-500 bg-muted/40 px-2.5 py-1.5 text-xs"
          >
            <CornerUpLeft className="mt-0.5 size-3.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
            <div className="min-w-0 flex-1">
              <div className="truncate font-semibold text-emerald-700 dark:text-emerald-300">{quotedLabel}</div>
              <div className="line-clamp-2 break-words text-muted-foreground" title={quoted.text}>
                {quoted.text}
              </div>
            </div>
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="size-5 shrink-0"
              aria-label="Cancel reply"
              onClick={() => setReplyToId('')}
            >
              <X className="size-3.5" />
            </Button>
          </div>
        ) : null}
        {staged ? (
          <div data-testid="chatbot-console-staged" className="flex items-start gap-1.5">
            {stagedUrl && staged.type.startsWith('image/') ? (
              <span className="relative inline-block size-14 overflow-hidden rounded-md border" title={staged.name}>
                <button
                  type="button"
                  className="block size-full"
                  aria-label={`Preview ${staged.name}`}
                  onClick={() => setPreviewOpen(true)}
                >
                  {/* A local object URL: next/image needs configured hosts. */}
                  <img src={stagedUrl} alt={staged.name} className="size-full object-cover" />
                </button>
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  className="absolute end-0 top-0 size-5 rounded-none bg-background/80"
                  aria-label={`Remove ${staged.name}`}
                  onClick={() => setStaged(null)}
                >
                  <X className="size-3" />
                </Button>
              </span>
            ) : (
              <span
                className="inline-flex max-w-full items-center gap-1 rounded-md border px-2 py-1 text-xs"
                title={staged.name}
              >
                <Mic className="size-3 shrink-0" />
                {stagedUrl ? (
                  <audio controls src={stagedUrl} aria-label={`Play ${staged.name}`} className="h-8 max-w-[220px]" />
                ) : (
                  <span className="truncate">{staged.name}</span>
                )}
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  className="size-4 shrink-0"
                  aria-label={`Remove ${staged.name}`}
                  onClick={() => setStaged(null)}
                >
                  <X className="size-3" />
                </Button>
              </span>
            )}
          </div>
        ) : null}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*,audio/*"
          aria-label="Attach image or audio"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0] ?? null;
            if (file) setStaged(file);
            e.target.value = '';
          }}
        />
        <div className="flex items-end gap-2">
          {voice.recording && voiceLocked ? (
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="text-destructive"
              aria-label="Delete recording"
              onClick={() => voice.cancel()}
            >
              <Trash2 className="size-4" />
            </Button>
          ) : !voice.recording ? (
            <Button
              type="button"
              variant="outline"
              size="icon"
              disabled={sending}
              onClick={() => fileInputRef.current?.click()}
              aria-label="Attach image or audio"
            >
              <Paperclip className="size-4" />
            </Button>
          ) : null}
          {recordingBar ?? (
            <Textarea
              ref={textareaRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onPaste={handlePaste}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="Ask, or attach voice/image"
              rows={2}
              disabled={sending}
              className="min-w-0 flex-1 resize-none"
            />
          )}
          {voice.recording && voiceLocked ? (
            <Button
              type="button"
              size="icon"
              aria-label="Send voice message"
              onClick={() => voice.stop()}
            >
              <SendHorizonal className="size-4" />
            </Button>
          ) : (
            <>
              <Button
                type="button"
                variant={holding || voice.recording ? 'destructive' : 'outline'}
                size="icon"
                // touch-none: the browser must not turn a held finger into a scroll.
                className="touch-none select-none"
                disabled={sending && !voice.recording}
                aria-label={
                  voice.recording
                    ? `Recording, ${formatElapsed(voice.seconds)}, release to send`
                    : 'Record voice message'
                }
                onPointerDown={onMicPointerDown}
                onPointerMove={onMicPointerMove}
                onPointerUp={onMicPointerUp}
                onPointerCancel={onMicPointerCancel}
                onContextMenu={(e) => e.preventDefault()}
              >
                <Mic className="size-4" />
              </Button>
              {!voice.recording ? (
                <Button
                  type="button"
                  size="icon"
                  disabled={sending || (!draft.trim() && !staged)}
                  onClick={handleSend}
                  aria-label={sending ? 'Sending' : 'Send message'}
                >
                  {sending ? <Loader2 className="size-4 animate-spin" /> : <SendHorizonal className="size-4" />}
                </Button>
              ) : null}
            </>
          )}
        </div>
      </div>

      <AttachmentPreviewModal
        open={previewOpen && !!stagedUrl}
        onOpenChange={setPreviewOpen}
        items={stagedUrl && staged ? [{ id: 'staged', name: staged.name, url: stagedUrl }] : []}
      />
    </div>
  );
}
