'use client';

import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  ExternalLink,
  MessageSquare,
  Search,
  SendHorizontal,
  Sparkles,
  TrendingDown,
  TrendingUp,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useCategoryOptions } from '../../hooks/useScmOptions';
import { useMarketSearch, useRunChat } from '../hooks/useExplainer';
import type { AskTurn, MarketSignal } from '../types/explainer.types';

/**
 * Plan assistant (M6) — the two "talk to / search for" surfaces that sit beside the
 * run's AI overview:
 *
 *  - **Discuss this plan** — a grounded, multi-turn chat over the WHOLE run (every
 *    recommendation + aggregates + matched market signals). The server reasons over
 *    the run's FROZEN numbers only; it never changes a quantity.
 *  - **Search the market** — an ad-hoc web search (Anthropic) keyed to a product
 *    category. Findings cache as market signals that then surface as advisory on the
 *    matching recommendations AND become visible to the chat above. Advisory-only —
 *    the planning maths is untouched (soft integration).
 */
export function PlanAssistant({ runId }: { runId: string }) {
  const [tab, setTab] = useState<'chat' | 'search' | null>(null);

  return (
    <Card className="p-0">
      <div className="flex flex-wrap items-center gap-2 border-b p-3">
        <div className="flex items-center gap-1.5 text-primary">
          <Sparkles className="size-4" aria-hidden />
          <span className="text-xs font-semibold uppercase tracking-wide">Plan assistant</span>
        </div>
        <div className="ms-auto flex gap-2">
          <Button
            type="button"
            variant={tab === 'chat' ? 'primary' : 'outline'}
            size="sm"
            onClick={() => setTab((t) => (t === 'chat' ? null : 'chat'))}
          >
            <MessageSquare className="size-4" aria-hidden />
            Discuss this plan
          </Button>
          <Button
            type="button"
            variant={tab === 'search' ? 'primary' : 'outline'}
            size="sm"
            onClick={() => setTab((t) => (t === 'search' ? null : 'search'))}
          >
            <Search className="size-4" aria-hidden />
            Search the market
          </Button>
        </div>
      </div>
      {tab === 'chat' ? <PlanChat runId={runId} /> : null}
      {tab === 'search' ? <MarketSearch /> : null}
      {tab === null ? (
        <p className="p-3 text-xs text-muted-foreground">
          Ask the AI about this plan (which buys are most urgent, why a supplier eats so much cash,
          what defers under a tighter budget) or search the market for a trend and let it surface as
          advisory on the matching products.
        </p>
      ) : null}
    </Card>
  );
}

/** Grounded, multi-turn chat over the whole run (M6-A). Transcript is local UI state;
 *  each turn forwards the prior transcript so follow-ups resolve. */
function PlanChat({ runId }: { runId: string }) {
  const [question, setQuestion] = useState('');
  const [turns, setTurns] = useState<AskTurn[]>([]);
  const chat = useRunChat(runId);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const q = question.trim();
    if (!q || chat.isPending) return;
    setQuestion('');
    try {
      const res = await chat.mutateAsync({
        question: q,
        history: turns.map((t) => ({ question: t.question, answer: t.answer })),
      });
      setTurns((prev) => [...prev, { question: q, answer: res.answer, refused: false }]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to answer question';
      setTurns((prev) => [...prev, { question: q, answer: msg, refused: true }]);
    }
  };

  return (
    <div className="space-y-3 p-3">
      {turns.length ? (
        <div className="max-h-80 space-y-3 overflow-y-auto pe-1">
          {turns.map((t, i) => (
            <div key={i} className="space-y-1">
              <div className="flex justify-end">
                <div className="max-w-[85%] rounded-lg bg-primary/10 px-3 py-1.5 text-sm">
                  {t.question}
                </div>
              </div>
              <div className="flex justify-start">
                <div
                  className={cn(
                    'flex max-w-[90%] items-start gap-1.5 rounded-lg px-3 py-1.5 text-sm',
                    t.refused ? 'bg-muted italic text-muted-foreground' : 'bg-muted',
                  )}
                >
                  <Sparkles className="mt-0.5 size-3.5 shrink-0 text-primary" aria-hidden />
                  <span className="whitespace-pre-wrap">{t.answer}</span>
                </div>
              </div>
            </div>
          ))}
          {chat.isPending ? (
            <div className="flex justify-start">
              <div className="flex max-w-[85%] items-center gap-1.5 rounded-lg bg-muted px-3 py-1.5">
                <Skeleton className="h-3.5 w-40" />
              </div>
            </div>
          ) : null}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">
          e.g. &ldquo;Which 5 buys are most urgent?&rdquo; · &ldquo;Why is so much cash going to one
          supplier?&rdquo; · &ldquo;What would defer if I cut the budget to RM 200k?&rdquo;
        </p>
      )}
      <form onSubmit={submit} className="flex items-center gap-2">
        <Input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask about this plan…"
          aria-label="Ask about this plan"
        />
        <Button type="submit" disabled={!question.trim() || chat.isPending}>
          <SendHorizontal className="size-4" aria-hidden />
          Ask
        </Button>
      </form>
    </div>
  );
}

const TREND_BADGE: Record<string, { label: string; variant: 'destructive' | 'success' | 'secondary'; Icon: typeof TrendingUp }> = {
  up: { label: 'Up', variant: 'destructive', Icon: TrendingUp },
  down: { label: 'Down', variant: 'success', Icon: TrendingDown },
};

/** Ad-hoc market search fired from planning (M6-B, soft). Keyed to a category so the
 *  finding surfaces as advisory on those recommendations + feeds the plan-chat. */
function MarketSearch() {
  const [query, setQuery] = useState('');
  const [categoryRef, setCategoryRef] = useState('');
  const [signals, setSignals] = useState<MarketSignal[] | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const { data: categoryOptions, isLoading: categoriesLoading } = useCategoryOptions();
  const search = useMarketSearch();
  const queryClient = useQueryClient();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const q = query.trim();
    if (!q || search.isPending) return;
    setNote(null);
    try {
      const res = await search.mutateAsync({ query: q, categoryRef: categoryRef || null });
      setSignals(res.signals);
      if (res.run.status === 'failed') {
        setNote(res.run.error || 'Search failed.');
      } else if (!res.signals.length) {
        setNote('No usable market signal found for that query.');
      } else if (!categoryRef) {
        setNote('Tip: pick a product category so the finding attaches to those products as advisory.');
      }
      // A fresh signal can change any rec's advisory — refetch open ones.
      void queryClient.invalidateQueries({ queryKey: ['scm', 'reorder', 'advisory'] });
    } catch (err) {
      setNote(err instanceof Error ? err.message : 'Search failed.');
      setSignals(null);
    }
  };

  return (
    <div className="space-y-3 p-3">
      <form onSubmit={submit} className="space-y-2">
        <div className="grid gap-2 sm:grid-cols-[1fr_220px]">
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. trending bathroom colours 2026"
            aria-label="Market search query"
          />
          <SearchableSelect
            value={categoryRef}
            onChange={setCategoryRef}
            options={categoryOptions ?? []}
            placeholder={categoriesLoading ? 'Loading categories…' : 'Category (optional)'}
            emptyMessage="No categories found."
            disabled={categoriesLoading}
          />
        </div>
        <Button type="submit" disabled={!query.trim() || search.isPending}>
          {search.isPending ? (
            <>
              <Search className="size-4 animate-pulse" aria-hidden />
              Searching the web…
            </>
          ) : (
            <>
              <Search className="size-4" aria-hidden />
              Search
            </>
          )}
        </Button>
      </form>

      {note ? <p className="text-xs text-muted-foreground">{note}</p> : null}

      {signals && signals.length ? (
        <div className="space-y-2">
          {signals.map((s) => {
            const trend = s.trend ? TREND_BADGE[s.trend] : undefined;
            return (
              <div
                key={s.id}
                className="flex items-start gap-2 rounded-lg border border-scm-incoming/40 bg-scm-incoming-soft p-3 text-sm"
              >
                <TrendingUp className="mt-0.5 size-4 shrink-0 text-scm-incoming" aria-hidden />
                <div className="min-w-0 space-y-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge variant="info" appearance="light" size="xs">
                      Market signal
                    </Badge>
                    {trend ? (
                      <Badge variant={trend.variant} appearance="light" size="xs">
                        <trend.Icon className="size-3" aria-hidden />
                        {trend.label}
                      </Badge>
                    ) : null}
                  </div>
                  <p>{s.summary}</p>
                  {s.source_url ? (
                    <a
                      href={s.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-2xs text-muted-foreground hover:text-foreground"
                    >
                      Source <ExternalLink className="size-3" aria-hidden />
                    </a>
                  ) : null}
                </div>
              </div>
            );
          })}
          <p className="text-2xs text-muted-foreground">
            Cached as advisory — open a matching product&apos;s explanation to see it, and the chat
            above can now reason about it. Quantities are unchanged.
          </p>
        </div>
      ) : null}
    </div>
  );
}
