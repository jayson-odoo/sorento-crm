'use client';

import { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  ArrowDownRight,
  ArrowUpRight,
  Bot,
  ExternalLink,
  GitCompareArrows,
  ListChecks,
  Minus,
  SendHorizontal,
  Sparkles,
  Sparkle,
  TrendingUp,
  X,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { fmtInt, fmtMoney } from '../../lib/format';
import { useRunChat } from '../hooks/useExplainer';
import type { M8ProposalLine } from '../lib/planRow';
import type {
  ActionProposal,
  ActionProposalLine,
  MarketProposalResult,
  PlanComparison,
  PlanComparisonRow,
  RunChatTurn,
} from '../types/explainer.types';

/** Shared markdown styling for assistant answers - mirrors the global AI bubble. */
const AI_MARKDOWN_CLASS =
  'space-y-2 text-sm leading-relaxed [&_p]:my-0 [&_ul]:my-1 [&_ol]:my-1 [&_ul]:list-disc [&_ol]:list-decimal [&_ul]:pl-5 [&_ol]:pl-5 [&_li]:my-0.5 [&_strong]:font-semibold [&_em]:italic [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-[0.9em]';

function AssistantMarkdown({ text }: { text: string }) {
  return (
    <div className={AI_MARKDOWN_CLASS}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  );
}

/** A proposal card's own line shape (from the market-proposal endpoint). */
interface ChatProposal {
  signal_summary: string | null;
  source_url: string | null;
  sources: { url: string; title: string | null }[];
  lines: M8ProposalLine[];
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  kind: 'text' | 'proposal';
  text: string;
  proposal?: ChatProposal;
  /** M8-F16: a resolved accept/reject/adjust action set the user Applies in one click. */
  actionProposal?: ActionProposal;
  /** M8-F: deterministic product-by-product comparison against previous plans. */
  comparison?: PlanComparison;
}

/** Map the market-proposal payload → the confirm-gated proposal card lines. Lines
 *  with no unit cost can't show a cash delta, so they're dropped (nothing to bump). */
function toChatProposal(res: MarketProposalResult): ChatProposal {
  return {
    signal_summary: res.signal_summary,
    source_url: res.source_url,
    sources: res.sources ?? [],
    lines: res.lines
      .filter((l) => l.unit_cost != null)
      .map((l) => ({
        row_id: l.rec_id,
        sku: l.sku ?? l.rec_id,
        product_name: l.product_name ?? '',
        old_qty: l.old_qty,
        new_qty: l.new_qty,
        unit_cost: l.unit_cost as number,
        reason: l.reason,
      })),
  };
}

/**
 * SCM M8 (slice E / M8-F6 / M8-F16) - ONE conversational surface over the REAL run. A
 * single Ask input: the backend answers grounded on today's plan + past plans (it
 * auto-injects past-plans for "previous / similar plans" questions, even with no SKU
 * named), and it AUTO-decides whether a question needs a live market web search. When a
 * scanned signal maps onto plan lines, the chat response carries a confirm-gated per-line
 * qty proposal. When the question is a plan INSTRUCTION ("buy FT-B only, reject the
 * rest"), the response carries a resolved accept/reject/adjust action set the user
 * Applies in one click - nothing changes until Apply, which routes each line through the
 * existing /accept, /reject and human-confirmed /adjust decision endpoints.
 */
export function PlanAssistant({
  runId,
  onApplyProposalLine,
  onApplyActions,
}: {
  runId: string | null;
  onApplyProposalLine: (line: M8ProposalLine) => void;
  onApplyActions: (lines: ActionProposalLine[]) => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState('');
  const [seq, setSeq] = useState(0);
  const endRef = useRef<HTMLDivElement | null>(null);

  const chat = useRunChat(runId);
  const thinking = chat.isPending;

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' });
  }, [messages.length, thinking]);

  const pushUser = (q: string) => {
    const id = `u-${seq}`;
    setSeq((s) => s + 1);
    setMessages((prev) => [...prev, { id, role: 'user', kind: 'text', text: q }]);
  };

  const historyFrom = (msgs: ChatMessage[]): RunChatTurn[] => {
    const turns: RunChatTurn[] = [];
    for (let i = 0; i < msgs.length - 1; i += 1) {
      if (msgs[i].role === 'user' && msgs[i + 1]?.role === 'assistant') {
        turns.push({ question: msgs[i].text, answer: msgs[i + 1].text });
      }
    }
    return turns;
  };

  const ask = async () => {
    const q = draft.trim();
    if (!q || thinking || !runId) return;
    const history = historyFrom(messages);
    setDraft('');
    pushUser(q);
    try {
      const res = await chat.mutateAsync({ question: q, history });
      const p = res.proposal ? toChatProposal(res.proposal) : null;
      const hasLines = !!p && p.lines.length > 0;
      const actionProposal =
        res.action_proposal && res.action_proposal.lines.length > 0
          ? res.action_proposal
          : undefined;
      const comparison =
        res.comparison && res.comparison.rows.length > 0 ? res.comparison : undefined;
      setMessages((prev) => [
        ...prev,
        {
          id: `a-${seq}`,
          role: 'assistant',
          kind: hasLines ? 'proposal' : 'text',
          text: res.answer,
          proposal: hasLines ? (p as ChatProposal) : undefined,
          actionProposal,
          comparison,
        },
      ]);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        {
          id: `a-${seq}`,
          role: 'assistant',
          kind: 'text',
          text: e instanceof Error ? e.message : 'Something went wrong answering that.',
        },
      ]);
    }
  };

  return (
    <Card className="p-0">
      <div className="flex items-center gap-1.5 border-b p-3 text-primary">
        <Sparkles className="size-4" aria-hidden />
        <span className="text-xs font-semibold uppercase tracking-wide">Plan assistant</span>
        <span className="ms-2 text-2xs font-normal normal-case text-muted-foreground">
          knows this plan · past plans · live market search
        </span>
      </div>

      <div className="space-y-3 p-3">
        {messages.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            Ask about today&apos;s plan (which buys eat the most cash, why a line defers), about
            past plans for a SKU, or about a market trend - I&apos;ll scan the market live and, when
            it maps onto your plan, propose confirm-gated qty changes. You can also instruct a
            change (&quot;buy FT-B only, reject the rest&quot;) and I&apos;ll propose the decisions
            for you to Apply.
          </p>
        ) : (
          <div className="max-h-[28rem] space-y-3 overflow-y-auto pe-1">
            {messages.map((m) =>
              m.role === 'user' ? (
                <div key={m.id} className="flex justify-end">
                  <div className="max-w-[85%] rounded-lg bg-primary/10 px-3 py-1.5 text-sm">
                    {m.text}
                  </div>
                </div>
              ) : (
                <div key={m.id} className="flex justify-start">
                  <div className="flex max-w-[92%] items-start gap-1.5 rounded-lg bg-muted px-3 py-2">
                    <Sparkles className="mt-0.5 size-3.5 shrink-0 text-primary" aria-hidden />
                    <div className="min-w-0 space-y-2">
                      <AssistantMarkdown text={m.text} />
                      {m.kind === 'proposal' && m.proposal ? (
                        <ProposalCard proposal={m.proposal} onApplyLine={onApplyProposalLine} />
                      ) : null}
                      {m.actionProposal ? (
                        <ActionCard proposal={m.actionProposal} onApply={onApplyActions} />
                      ) : null}
                      {m.comparison ? <ComparisonCard comparison={m.comparison} /> : null}
                    </div>
                  </div>
                </div>
              ),
            )}
            {thinking ? <ThinkingBubble /> : null}
            <div ref={endRef} />
          </div>
        )}

        <form
          onSubmit={(e) => {
            e.preventDefault();
            void ask();
          }}
          className="flex items-center gap-2"
        >
          <Input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Ask about this plan, past plans, or a market trend..."
            aria-label="Ask the plan assistant"
            disabled={!runId}
          />
          <Button type="submit" disabled={thinking || !draft.trim() || !runId}>
            <SendHorizontal className="size-4" aria-hidden />
            Ask
          </Button>
        </form>
      </div>
    </Card>
  );
}

function ThinkingBubble() {
  return (
    <div className="flex justify-start">
      <div className="rounded-lg bg-muted p-3 text-sm">
        <div className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
          <Bot className="size-3.5 animate-pulse" aria-hidden />
          Thinking...
        </div>
        <div className="flex items-center gap-1">
          <span className="size-2 animate-bounce rounded-full bg-muted-foreground/70 [animation-delay:-0.3s]" />
          <span className="size-2 animate-bounce rounded-full bg-muted-foreground/70 [animation-delay:-0.15s]" />
          <span className="size-2 animate-bounce rounded-full bg-muted-foreground/70" />
        </div>
      </div>
    </div>
  );
}

/** Short host label for a source url (drops www.), e.g. "statista.com". */
function hostLabel(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

/** Citation sources for a market signal (M8-F): clickable external links that prove the
 *  figure is factual. Several when the search returned them, one for legacy signals. */
function SourceLinks({ sources }: { sources: { url: string; title: string | null }[] }) {
  if (!sources || sources.length === 0) return null;
  return (
    <div className="mb-2 flex flex-wrap items-center gap-1.5">
      <span className="text-2xs font-medium text-muted-foreground">
        Source{sources.length === 1 ? '' : 's'}:
      </span>
      {sources.map((s) => (
        <a
          key={s.url}
          href={s.url}
          target="_blank"
          rel="noreferrer noopener"
          title={s.title ?? s.url}
          className="inline-flex max-w-[14rem] items-center gap-1 truncate rounded-md border bg-background px-1.5 py-0.5 text-2xs text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <ExternalLink className="size-3 shrink-0" aria-hidden />
          <span className="truncate">{s.title || hostLabel(s.url)}</span>
        </a>
      ))}
    </div>
  );
}

/** A confirm-gated market-bump proposal (M8-E5): per-line old->new qty + reason,
 *  each Confirm/Dismiss individually. Confirm fires a real /adjust override. */
function ProposalCard({
  proposal,
  onApplyLine,
}: {
  proposal: ChatProposal;
  onApplyLine: (line: M8ProposalLine) => void;
}) {
  const [resolved, setResolved] = useState<Record<string, 'confirmed' | 'dismissed'>>({});

  return (
    <div className="rounded-lg border border-scm-incoming/40 bg-scm-incoming-soft/40 p-2.5">
      <div className="mb-1.5 flex items-center gap-1.5">
        <Badge variant="info" appearance="light" size="xs">
          <TrendingUp className="size-3" aria-hidden />
          Market signal
        </Badge>
        <span className="text-2xs text-muted-foreground">Include in plan?</span>
      </div>
      {proposal.signal_summary ? (
        <p className="mb-2 text-xs text-muted-foreground">{proposal.signal_summary}</p>
      ) : null}
      <SourceLinks sources={proposal.sources} />
      <div className="space-y-1.5">
        {proposal.lines.map((line) => {
          const state = resolved[line.row_id];
          const oldCash = line.old_qty * line.unit_cost;
          const newCash = line.new_qty * line.unit_cost;
          return (
            <div
              key={line.row_id}
              className={cn(
                'flex flex-wrap items-center gap-2 rounded-md border bg-background px-2.5 py-1.5 text-xs',
                state === 'dismissed' && 'opacity-50',
              )}
            >
              <span className="font-medium">{line.sku}</span>
              <span className="tabular-nums text-muted-foreground">
                {fmtInt(line.old_qty)} &rarr;{' '}
                <span className="font-semibold text-foreground">{fmtInt(line.new_qty)}</span>
              </span>
              <span className="tabular-nums text-muted-foreground">
                ({fmtMoney(oldCash)} &rarr; {fmtMoney(newCash)})
              </span>
              <span className="min-w-0 flex-1 truncate text-2xs text-muted-foreground" title={line.reason}>
                {line.reason}
              </span>
              {state ? (
                <Badge
                  variant={state === 'confirmed' ? 'success' : 'secondary'}
                  appearance="light"
                  size="xs"
                >
                  {state === 'confirmed' ? 'Applied' : 'Dismissed'}
                </Badge>
              ) : (
                <span className="flex gap-1">
                  <Button
                    size="sm"
                    className="h-6 px-2 text-2xs"
                    onClick={() => {
                      onApplyLine(line);
                      setResolved((r) => ({ ...r, [line.row_id]: 'confirmed' }));
                    }}
                  >
                    Confirm
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 px-2 text-2xs"
                    onClick={() => setResolved((r) => ({ ...r, [line.row_id]: 'dismissed' }))}
                  >
                    Dismiss
                  </Button>
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Format a nullable qty, dash when the engine had no value. */
function q(v: number | null): string {
  return v === null || v === undefined ? '—' : fmtInt(v);
}

const DECISION_LABEL: Record<string, string> = {
  proposed: 'suggested',
  accepted: 'bought',
  adjusted: 'bought (adjusted)',
  dismissed: 'rejected',
};

/** The change chip for a comparison row - direction + signed qty delta, coloured. */
function ChangeChip({ row }: { row: PlanComparisonRow }) {
  if (row.direction === 'new') {
    return (
      <Badge variant="info" appearance="light" size="xs">
        <Sparkle className="size-3" aria-hidden />
        New
      </Badge>
    );
  }
  if (row.direction === 'same') {
    return (
      <span className="inline-flex items-center gap-1 text-2xs text-muted-foreground">
        <Minus className="size-3" aria-hidden />
        No change
      </span>
    );
  }
  const up = row.direction === 'up';
  const delta = row.qty_delta ?? 0;
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 text-2xs font-medium tabular-nums',
        up ? 'text-scm-incoming' : 'text-scm-stockout',
      )}
    >
      {up ? <ArrowUpRight className="size-3" aria-hidden /> : <ArrowDownRight className="size-3" aria-hidden />}
      {up ? '+' : ''}
      {fmtInt(delta)}
    </span>
  );
}

/** M8-F: a DETERMINISTIC product-by-product comparison of this plan vs each product's
 *  most recent prior plan. Every number here is a frozen engine value diffed server-side
 *  in Python - the assistant's prose never restates them, so no LLM does the arithmetic.
 *  Laid out as a roomy card list (SKU + previous->current + change on one line, the why
 *  on its own line) so it stays legible instead of a cramped table. */
function ComparisonCard({ comparison }: { comparison: PlanComparison }) {
  return (
    <div className="overflow-hidden rounded-lg border border-primary/30 bg-primary/5">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-primary/20 px-3 py-2">
        <Badge variant="primary" appearance="light" size="xs">
          <GitCompareArrows className="size-3" aria-hidden />
          Plan vs previous
        </Badge>
        <span className="text-2xs text-muted-foreground">
          {comparison.compared_count} of {comparison.rows.length} planned before · exact figures
        </span>
      </div>
      <div className="divide-y divide-primary/10">
        {comparison.rows.map((row) => (
          <div key={row.sku ?? row.product_name ?? Math.random().toString()} className="px-3 py-2.5">
            <div className="flex items-center justify-between gap-3">
              <span className="min-w-0 truncate text-sm font-semibold" title={row.sku ?? undefined}>
                {row.sku ?? row.product_name}
              </span>
              <ChangeChip row={row} />
            </div>
            <div className="mt-1.5 flex items-center gap-2 text-xs">
              <span className="inline-flex flex-col items-start rounded-md bg-background px-2 py-1">
                <span className="text-[0.6rem] uppercase tracking-wide text-muted-foreground">Previous</span>
                <span className="font-medium tabular-nums">
                  {row.previous_qty === null ? '—' : q(row.previous_qty)}
                  {row.previous_decision ? (
                    <span className="ms-1 font-normal text-muted-foreground">
                      {DECISION_LABEL[row.previous_decision] ?? row.previous_decision}
                    </span>
                  ) : null}
                </span>
              </span>
              <span className="text-muted-foreground" aria-hidden>
                &rarr;
              </span>
              <span className="inline-flex flex-col items-start rounded-md bg-background px-2 py-1">
                <span className="text-[0.6rem] uppercase tracking-wide text-muted-foreground">Now</span>
                <span className="font-medium tabular-nums">{q(row.current_qty)}</span>
              </span>
            </div>
            <p className="mt-1.5 text-2xs leading-relaxed text-muted-foreground">{row.reason}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

const ACTION_LABEL: Record<ActionProposalLine['action'], string> = {
  accept: 'Accept',
  reject: 'Reject',
  adjust: 'Adjust',
};

const ACTION_BADGE: Record<ActionProposalLine['action'], 'success' | 'destructive' | 'warning'> = {
  accept: 'success',
  reject: 'destructive',
  adjust: 'warning',
};

/** A confirm-gated plan-action proposal (M8-F16): the assistant resolved a
 *  natural-language instruction into per-line accept/reject/adjust decisions. Apply
 *  routes every kept line through the existing /accept, /reject and /adjust handlers in
 *  ONE click (the click IS the confirmation); each line can be dismissed before Apply. */
function ActionCard({
  proposal,
  onApply,
}: {
  proposal: ActionProposal;
  onApply: (lines: ActionProposalLine[]) => void;
}) {
  const [applied, setApplied] = useState(false);
  const [dismissed, setDismissed] = useState<Record<string, true>>({});
  const active = proposal.lines.filter((l) => !dismissed[l.rec_id]);

  return (
    <div className="rounded-lg border border-primary/40 bg-primary/5 p-2.5">
      <div className="mb-1.5 flex items-center gap-1.5">
        <Badge variant="primary" appearance="light" size="xs">
          <ListChecks className="size-3" aria-hidden />
          Plan actions
        </Badge>
        <span className="text-2xs text-muted-foreground">Apply to plan?</span>
      </div>
      {proposal.summary ? (
        <p className="mb-2 text-xs text-muted-foreground">{proposal.summary}</p>
      ) : null}
      <div className="space-y-1.5">
        {proposal.lines.map((line) => {
          const isDismissed = !!dismissed[line.rec_id];
          return (
            <div
              key={line.rec_id}
              className={cn(
                'flex flex-wrap items-center gap-2 rounded-md border bg-background px-2.5 py-1.5 text-xs',
                isDismissed && 'opacity-50',
              )}
            >
              <Badge variant={ACTION_BADGE[line.action]} appearance="light" size="xs">
                {ACTION_LABEL[line.action]}
              </Badge>
              <span className="font-medium">{line.sku ?? line.product_name ?? line.rec_id}</span>
              {line.action === 'adjust' && line.new_qty != null ? (
                <span className="tabular-nums text-muted-foreground">
                  {fmtInt(line.current_qty ?? 0)} &rarr;{' '}
                  <span className="font-semibold text-foreground">{fmtInt(line.new_qty)}</span>
                </span>
              ) : null}
              <span
                className="min-w-0 flex-1 truncate text-2xs text-muted-foreground"
                title={line.reason}
              >
                {line.reason}
              </span>
              {!applied && !isDismissed ? (
                <Button
                  variant="ghost"
                  size="sm"
                  className="size-6 p-0 text-muted-foreground"
                  aria-label={`Dismiss ${line.sku ?? line.product_name ?? 'line'}`}
                  onClick={() => setDismissed((d) => ({ ...d, [line.rec_id]: true }))}
                >
                  <X className="size-3.5" aria-hidden />
                </Button>
              ) : null}
            </div>
          );
        })}
      </div>
      <div className="mt-2 flex items-center justify-end">
        {applied ? (
          <Badge variant="success" appearance="light" size="sm">
            Applied
          </Badge>
        ) : (
          <Button
            size="sm"
            className="h-7 px-3 text-2xs"
            disabled={active.length === 0}
            onClick={() => {
              onApply(active);
              setApplied(true);
            }}
          >
            Apply {active.length} action{active.length === 1 ? '' : 's'}
          </Button>
        )}
      </div>
    </div>
  );
}
