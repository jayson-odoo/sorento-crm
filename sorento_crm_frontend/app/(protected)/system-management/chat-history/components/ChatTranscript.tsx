'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, ChevronUp, Search, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import type { ChatMessageRow } from '../types/chatHistory.types';
import { StateTracePanel } from './StateTracePanel';

interface ChatTranscriptProps {
  messages: ChatMessageRow[];
  isLoading?: boolean;
  /** Message to centre on and ring-highlight when there is no active search. */
  anchorId?: number | null;
  emptyText?: string;
}

function latencyVariant(seconds: number): string {
  return seconds > 30 ? 'destructive' : seconds > 10 ? 'warning' : 'success';
}

function fmtLatency(seconds: number): string {
  return seconds < 1 ? `${Math.round(seconds * 1000)}ms` : `${seconds.toFixed(1)}s`;
}

/** Split a message into segments, marking the ones that match `term` (case-insensitive). */
function highlight(text: string, term: string): { text: string; hit: boolean }[] {
  if (!term) return [{ text, hit: false }];
  const lower = text.toLowerCase();
  const q = term.toLowerCase();
  const out: { text: string; hit: boolean }[] = [];
  let i = 0;
  while (i < text.length) {
    const found = lower.indexOf(q, i);
    if (found === -1) {
      out.push({ text: text.slice(i), hit: false });
      break;
    }
    if (found > i) out.push({ text: text.slice(i, found), hit: false });
    out.push({ text: text.slice(found, found + q.length), hit: true });
    i = found + q.length;
  }
  return out;
}

export function ChatTranscript({ messages, isLoading, anchorId, emptyText }: ChatTranscriptProps) {
  const [term, setTerm] = useState('');
  const [activeMatch, setActiveMatch] = useState(0);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const anchorRef = useRef<HTMLDivElement | null>(null);
  const matchRefs = useRef<(HTMLDivElement | null)[]>([]);

  // Message ids that contain the term, in transcript order - the navigable match set.
  const matches = useMemo(() => {
    const q = term.trim().toLowerCase();
    if (!q) return [] as number[];
    return messages.filter((m) => m.message.toLowerCase().includes(q)).map((m) => m.id);
  }, [messages, term]);

  useEffect(() => {
    setActiveMatch(0);
  }, [term]);

  // Jump to the active match as the user steps through them.
  useEffect(() => {
    if (!matches.length) return;
    const el = matchRefs.current[activeMatch];
    el?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [activeMatch, matches]);

  // With no search, land on the clicked message (bot replies can be very long).
  useEffect(() => {
    if (isLoading || term || !messages.length) return;
    const id = window.requestAnimationFrame(() =>
      anchorRef.current?.scrollIntoView({ block: 'center' }),
    );
    return () => window.cancelAnimationFrame(id);
  }, [isLoading, term, messages, anchorId]);

  const step = (delta: number) => {
    if (!matches.length) return;
    setActiveMatch((i) => (i + delta + matches.length) % matches.length);
  };

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-2 border-b bg-background/80 sticky top-0 z-10">
        <div className="relative flex items-center gap-2">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
          <Input
            className="pl-9 pr-2 h-9"
            placeholder="Search in conversation"
            value={term}
            onChange={(e) => setTerm(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') step(e.shiftKey ? -1 : 1);
            }}
          />
          {term && (
            <div className="flex items-center gap-1 shrink-0">
              <span className="text-xs text-muted-foreground tabular-nums min-w-14 text-right">
                {matches.length ? `${activeMatch + 1} / ${matches.length}` : '0 / 0'}
              </span>
              <Button
                variant="outline"
                size="icon"
                className="size-8"
                disabled={!matches.length}
                onClick={() => step(-1)}
                aria-label="Previous match"
              >
                <ChevronUp className="size-4" />
              </Button>
              <Button
                variant="outline"
                size="icon"
                className="size-8"
                disabled={!matches.length}
                onClick={() => step(1)}
                aria-label="Next match"
              >
                <ChevronDown className="size-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="size-8"
                onClick={() => setTerm('')}
                aria-label="Clear search"
              >
                <X className="size-4" />
              </Button>
            </div>
          )}
        </div>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {isLoading && (
          <>
            <Skeleton className="h-16 w-3/4" />
            <Skeleton className="h-16 w-3/4 ml-auto" />
            <Skeleton className="h-16 w-2/3" />
          </>
        )}

        {!isLoading && messages.length === 0 && (
          <div className="text-center py-12">
            <p className="text-sm text-muted-foreground">
              {emptyText ?? 'No messages stored for this contact.'}
            </p>
          </div>
        )}

        {!isLoading &&
          messages.map((m) => {
            const outgoing = m.type === 'outgoing';
            const isAnchor = m.id === anchorId;
            const matchIdx = matches.indexOf(m.id);
            const isMatch = matchIdx !== -1;
            const isActive = isMatch && matchIdx === activeMatch;
            return (
              <div
                key={m.id}
                ref={(el) => {
                  if (isAnchor) anchorRef.current = el;
                  if (isMatch) matchRefs.current[matchIdx] = el;
                }}
                className={`flex ${outgoing ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={[
                    'max-w-[85%] rounded-lg px-3 py-2 text-sm',
                    outgoing ? 'bg-primary/10' : 'bg-muted',
                    isActive ? 'ring-2 ring-amber-500' : isAnchor && !term ? 'ring-2 ring-primary' : '',
                  ].join(' ')}
                >
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <span className="text-[11px] text-muted-foreground">
                      {formatDateTimeInMalaysia(m.sent_at)}
                    </span>
                    {m.latency_seconds != null && (
                      <Badge variant={latencyVariant(m.latency_seconds) as never} className="ml-2 shrink-0">
                        {fmtLatency(m.latency_seconds)}
                      </Badge>
                    )}
                  </div>
                  <p className="whitespace-pre-wrap break-words">
                    {highlight(m.message, term.trim()).map((seg, i) =>
                      seg.hit ? (
                        <mark key={i} className="bg-amber-200 text-inherit rounded-sm">
                          {seg.text}
                        </mark>
                      ) : (
                        <span key={i}>{seg.text}</span>
                      ),
                    )}
                  </p>
                  {m.delivery_status && (
                    <span className="text-[11px] text-muted-foreground">{m.delivery_status}</span>
                  )}
                  {/* Diagnosis surface: incoming rows carry the per-turn state trace. */}
                  {!outgoing && m.state_trace && <StateTracePanel trace={m.state_trace} />}
                </div>
              </div>
            );
          })}
      </div>
    </div>
  );
}
