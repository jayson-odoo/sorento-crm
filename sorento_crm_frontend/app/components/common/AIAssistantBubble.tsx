'use client';

import Link from 'next/link';
import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { Bot, Loader2, SendHorizonal, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { sendAIAssistantMessage, type AIAssistantMessage } from '@/lib/aiAssistantChatApi';
import { useHasPermission } from '@/hooks/usePermissions';

export default function AIAssistantBubble() {
  const canUseAIAssistant = useHasPermission('system.ai_assistant_chat.use');
  const [open, setOpen] = useState(false);
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);
  const [messages, setMessages] = useState<AIAssistantMessage[]>([]);
  const [input, setInput] = useState('');
  const [isSending, setIsSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const canSend = input.trim().length > 0 && !isSending;

  const sortedMessages = useMemo(
    () => [...messages].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()),
    [messages],
  );

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [sortedMessages.length, isSending]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!canSend) return;
    const text = input.trim();
    setInput('');
    const optimistic: AIAssistantMessage = {
      id: `temp-user-${Date.now()}`,
      role: 'user',
      content: text,
      metadata_json: {},
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimistic]);
    setIsSending(true);
    try {
      const conv = await sendAIAssistantMessage(text, conversationId);
      setConversationId(conv.id);
      setMessages(conv.messages || []);
    } catch (err) {
      const errorMessage: AIAssistantMessage = {
        id: `temp-error-${Date.now()}`,
        role: 'assistant',
        content: (err as Error)?.message || 'Failed to get assistant response.',
        metadata_json: {},
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsSending(false);
    }
  };

  if (!canUseAIAssistant) return null;

  return (
    <div className="fixed bottom-6 right-6 z-[120]">
      <Button
        size="icon"
        className={`size-12 rounded-full shadow-lg transition-transform ${isSending ? 'animate-pulse' : ''}`}
        aria-label="Open AI assistant"
        onClick={() => setOpen((o) => !o)}
      >
        <Bot className="size-5" />
      </Button>

      {open ? (
        <div className="absolute bottom-16 right-0 flex h-[72vh] w-[min(900px,calc(100vw-2rem))] flex-col overflow-hidden rounded-2xl border border-border/60 bg-gradient-to-b from-background to-muted/40 shadow-2xl backdrop-blur-sm">
          <div className="flex items-center justify-between border-b border-border/70 bg-background/80 px-4 py-3">
            <h3 className="text-base font-semibold">AI assistant</h3>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="rounded-full"
              onClick={() => setOpen(false)}
              aria-label="Close AI assistant"
            >
              <X className="size-4" />
            </Button>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            <div className="space-y-3">
              {sortedMessages.length === 0 ? (
                <p className="rounded-xl bg-background/70 p-3 text-sm text-muted-foreground">
                  Ask a CRM question to test MCP and embeddings.
                </p>
              ) : null}
              {sortedMessages.map((m) => (
                <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div
                    className={`max-w-[85%] rounded-2xl px-3 py-2.5 text-sm leading-relaxed shadow-sm ${
                      m.role === 'user'
                        ? 'bg-primary/15 text-foreground'
                        : 'bg-background/85 text-foreground'
                    }`}
                  >
                    <p className="whitespace-pre-wrap">{m.content}</p>
                    {m.role === 'assistant' && m.metadata_json?.links?.length ? (
                      <div className="mt-2 space-y-1">
                        {m.metadata_json.links.map((href) => (
                          <Link key={href} href={href} className="block text-xs text-primary hover:underline">
                            {href}
                          </Link>
                        ))}
                      </div>
                    ) : null}
                  </div>
                </div>
              ))}
              {isSending ? (
                <div className="flex justify-start">
                  <div className="rounded-2xl bg-background/85 p-3 text-sm shadow-sm">
                    <div className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
                      <Bot className="size-3.5 animate-pulse" />
                      Thinking...
                    </div>
                    <div className="flex items-center gap-1">
                      <span className="size-2 animate-bounce rounded-full bg-muted-foreground/70 [animation-delay:-0.3s]" />
                      <span className="size-2 animate-bounce rounded-full bg-muted-foreground/70 [animation-delay:-0.15s]" />
                      <span className="size-2 animate-bounce rounded-full bg-muted-foreground/70" />
                    </div>
                  </div>
                </div>
              ) : null}
              <div ref={messagesEndRef} />
            </div>
          </div>

          <form onSubmit={onSubmit} className="border-t border-border/70 bg-background/85 p-3">
            <div className="flex items-center gap-2">
              <Input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask the assistant..."
                className="rounded-xl"
              />
              <Button type="submit" size="icon" className="rounded-xl" disabled={!canSend}>
                {isSending ? <Loader2 className="size-4 animate-spin" /> : <SendHorizonal className="size-4" />}
              </Button>
            </div>
          </form>
        </div>
      ) : null}
    </div>
  );
}
