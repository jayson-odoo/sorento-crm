'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { Loader2, RotateCcw, SendHorizonal } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import { cn } from '@/lib/utils';
import { getRespondContactsOutbound } from '../../respond-contacts/services/respondContactOutboundService';
import { useChatbotConsole } from '../hooks/useChatbotConsole';
import type { ChatbotConsoleMessage } from '../types/chatbotConsole.types';

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

function promptVersionLabel(version: { version: number; label: string | null; chars: number }): string {
  const base = `v${version.version} - ${version.chars} chars`;
  return version.label ? `${base} (${version.label})` : base;
}

function MessageBubble({
  message,
  onQuickReply,
}: {
  message: ChatbotConsoleMessage;
  onQuickReply: (text: string) => void;
}) {
  const isUser = message.role === 'user';
  return (
    <div className={cn('flex', isUser ? 'justify-end' : 'justify-start')}>
      <div
        className={cn(
          'max-w-[85%] rounded-2xl px-3 py-2.5 text-sm leading-relaxed shadow-sm',
          isUser ? 'bg-primary/15 text-foreground' : 'bg-muted text-foreground',
        )}
      >
        <p className="whitespace-pre-wrap break-words">{message.text}</p>
        {message.branchKind ? (
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <Badge variant="secondary" size="sm">
              {message.branchKind}
            </Badge>
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
      </div>
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
    messages,
    sending,
    sendText,
    sendQuickReply,
    reset,
  } = useChatbotConsole();

  const [draft, setDraft] = useState('');
  const threadEndRef = useRef<HTMLDivElement | null>(null);

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

  const handleSend = () => {
    if (!draft.trim() || sending) return;
    const text = draft;
    setDraft('');
    void sendText(text);
  };

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

      {/* Thread - the ONLY scrolling region. */}
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1" data-testid="chatbot-console-thread">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} onQuickReply={sendQuickReply} />
        ))}
        {sending ? <TypingIndicator /> : null}
        <div ref={threadEndRef} />
      </div>

      {/* Composer - pinned at the bottom. */}
      <div className="border-t pt-3">
        <div className="flex items-end gap-2">
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
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
          <Button
            type="button"
            size="icon"
            disabled={sending || !draft.trim()}
            onClick={handleSend}
            aria-label={sending ? 'Sending' : 'Send message'}
          >
            {sending ? <Loader2 className="size-4 animate-spin" /> : <SendHorizonal className="size-4" />}
          </Button>
        </div>
      </div>
    </div>
  );
}
