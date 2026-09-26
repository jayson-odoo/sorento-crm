'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Badge, type BadgeProps } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { SearchableCode } from '@/components/common/find-in-text/SearchableCode';
import { useChatbotTurn } from '../hooks/useChatbotTurns';
import { shortTurnId } from '../turnPresentation';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import type {
  TurnDetail,
  TurnDetailApplyDiff,
  TurnDetailApplyDiffEntry,
  TurnDetailContextLayer,
  TurnDetailCrossdomain,
  TurnDetailDecay,
  TurnDetailFocus,
  TurnDetailOrderNeighbor,
} from '../types/chatbotTurn.types';

/**
 * Turn detail trace view (chatbot growth r1, Slice D2, AC-972, AC-973).
 *
 * `TurnPanel` (the existing per-stage timeline under a message) already answers
 * "what happened, in order". This answers a narrower question an engineer opens
 * a specific turn to ask: what did the tool call actually carry, what did a
 * cross-domain probe find, which field-reveal keys were dropped, which focus
 * rule fired and why, what did the session gain or lose. Each section renders
 * whatever the backend composed and collapses to nothing wasted when a kind
 * has not shipped yet - never an error, never a placeholder explaining why.
 */
export function TurnDetailDrawer({
  turnId,
  onOpenChange,
}: {
  turnId: string | null;
  onOpenChange: (open: boolean) => void;
}) {
  const { data: turn, isLoading, isError } = useChatbotTurn(turnId);

  return (
    <Sheet open={Boolean(turnId)} onOpenChange={onOpenChange}>
      <SheetContent
        className="w-full sm:max-w-2xl flex flex-col p-0 overflow-x-hidden"
        aria-describedby={undefined}
      >
        <SheetHeader className="px-4 sm:px-6 py-4 border-b">
          <SheetTitle className="truncate">
            {turn ? `Turn #${shortTurnId(turn.id)}` : turnId ? `Turn #${shortTurnId(turnId)}` : 'Turn'}
          </SheetTitle>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto overflow-x-hidden px-4 sm:px-6 py-4 space-y-3">
          {isLoading && (
            <div className="space-y-2" data-testid="turn-detail-loading">
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          )}
          {isError && (
            <p className="text-sm text-destructive">
              Could not load this turn. Reload to try again.
            </p>
          )}
          {turn && <Sections detail={turn.trace_detail} />}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function Sections({ detail }: { detail: TurnDetail }) {
  return (
    <>
      <Section title="Order" testId="section-order" defaultOpen>
        <OrderSection order={detail.order ?? null} />
      </Section>
      <Section title="Stages" testId="section-stages" defaultOpen>
        <StagesSection stages={detail.stages} />
      </Section>
      <Section title="Parse" testId="section-parse">
        <ParseSection parse={detail.parse} />
      </Section>
      <Section title="Apply" testId="section-apply">
        <ApplySection apply={detail.apply ?? null} />
      </Section>
      <Section title="Memory" testId="section-memory">
        <MemorySection memory={detail.memory ?? null} />
      </Section>
      <Section title="Context sent to the AI" testId="section-context">
        <ContextSection context={detail.context ?? null} />
      </Section>
      <Section title="Decay" testId="section-decay">
        <DecaySection decay={detail.decay} />
      </Section>
      <Section title="Open question" testId="section-open-question">
        <OpenQuestionSection openQuestion={detail.open_question} />
      </Section>
      <Section title="Focus" testId="section-focus">
        <FocusSection focus={detail.focus} />
      </Section>
      <Section title="Tool" testId="section-tool">
        <ToolSection tool={detail.tool} />
      </Section>
      <Section title="Cross-domain" testId="section-crossdomain">
        <CrossdomainSection crossdomain={detail.crossdomain} />
      </Section>
      <Section title="Field reveals" testId="section-reveals">
        <RevealsSection reveals={detail.reveals} />
      </Section>
      <Section title="Session" testId="section-session">
        <SessionSection session={detail.session} />
      </Section>
      <Section title="Sent" testId="section-sent">
        <SentSection stages={detail.stages} />
      </Section>
    </>
  );
}

function Section({
  title,
  testId,
  defaultOpen = false,
  children,
}: {
  title: string;
  testId: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Collapsible open={open} onOpenChange={setOpen} className="rounded-lg border">
      <CollapsibleTrigger
        className="flex w-full items-center gap-1.5 px-3 py-2 text-start text-sm font-medium"
        data-testid={`${testId}-trigger`}
      >
        {open ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
        {title}
      </CollapsibleTrigger>
      <CollapsibleContent data-testid={testId}>
        <div className="border-t px-3 py-2">{children}</div>
      </CollapsibleContent>
    </Collapsible>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="text-xs text-muted-foreground">{children}</p>;
}

function Code({ value }: { value: unknown }) {
  return (
    <div className="overflow-x-auto">
      <SearchableCode text={JSON.stringify(value, null, 2)} />
    </div>
  );
}

/**
 * The `sent` stage as its own panel (browser pass 1, 16 Sep 2026): every stage the
 * trace carries must render as a panel, and the hand-off to the caller was the one
 * that only appeared as a row inside Stages. Read off the stage record itself - the
 * engine records "Handed the reply to the caller to send." with the action count.
 */
function SentSection({ stages }: { stages: TurnDetail['stages'] }) {
  const sent = stages.find((stage) => stage.name === 'sent');
  if (!sent) return <Empty>No sent stage recorded.</Empty>;
  return (
    <div className="space-y-1 text-xs">
      <div className="flex items-center gap-2">
        <Badge
          variant={sent.status === 'failed' ? 'destructive' : 'success'}
          appearance="light"
          size="sm"
        >
          {sent.status ?? 'ok'}
        </Badge>
        {sent.ms != null && <span className="text-muted-foreground tabular-nums">{sent.ms}ms</span>}
      </div>
      {sent.status === 'failed' && sent.error ? (
        <p className="rounded-md border border-destructive/30 bg-destructive/5 px-2 py-1.5 text-destructive">
          {sent.error}
        </p>
      ) : sent.summary ? (
        <p className="text-muted-foreground">{sent.summary}</p>
      ) : null}
    </div>
  );
}

function StagesSection({ stages }: { stages: TurnDetail['stages'] }) {
  if (stages.length === 0) return <Empty>No stages recorded.</Empty>;
  return (
    <ol className="space-y-2">
      {stages.map((stage, i) => (
        <li key={`${stage.name}-${i}`} className="text-xs">
          <div className="flex items-center gap-2">
            <Badge
              variant={stage.status === 'failed' ? 'destructive' : 'success'}
              appearance="light"
              size="sm"
            >
              {stage.name}
            </Badge>
            {stage.ms != null && (
              <span className="text-muted-foreground tabular-nums">{stage.ms}ms</span>
            )}
          </div>
          {stage.status === 'failed' && stage.error ? (
            <p className="mt-1 rounded-md border border-destructive/30 bg-destructive/5 px-2 py-1.5 text-destructive">
              {stage.error}
            </p>
          ) : stage.summary ? (
            <p className="mt-1 text-muted-foreground">{stage.summary}</p>
          ) : null}
          {/* Browser pass, chatbot media-into-turn: the same flattened facts
              TurnPanel's own inline StageRow prints - a media turn's `media_intake`
              stage carries modality/decision/entities/attributes/notes here. */}
          {Object.keys(stage.facts ?? {}).length > 0 && (
            <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-2.5 gap-y-0.5">
              {Object.entries(stage.facts ?? {}).map(([key, value]) => (
                <div key={key} className="contents">
                  <dt className="text-muted-foreground">{key.replace(/_/g, ' ')}</dt>
                  <dd className="min-w-0 truncate" title={String(value)}>
                    {String(value)}
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </li>
      ))}
    </ol>
  );
}

function ParseSection({ parse }: { parse: TurnDetail['parse'] }) {
  if (!parse) return <Empty>No parse recorded.</Empty>;
  return (
    <div className="space-y-2 text-xs">
      <dl className="grid grid-cols-[auto_1fr] gap-x-2.5 gap-y-0.5">
        <dt className="text-muted-foreground">prompt version</dt>
        <dd>{parse.prompt_version ?? '-'}</dd>
        <dt className="text-muted-foreground">model</dt>
        <dd>{parse.model ?? '-'}</dd>
      </dl>
      {parse.post_processed && (
        <div>
          <div className="mb-1 font-medium text-muted-foreground">Post-processed</div>
          <Code value={parse.post_processed} />
        </div>
      )}
      {parse.raw && (
        <div>
          <div className="mb-1 font-medium text-muted-foreground">Raw</div>
          <Code value={parse.raw} />
        </div>
      )}
    </div>
  );
}

/**
 * The state diff as one list, whichever shape the turn carries it in.
 *
 * `turn_runtime.focus_diff` sends a MAP keyed by focus slot and the panel called
 * `.map()` on it, which threw `apply.state_diff.map is not a function` and took the
 * whole drawer down with an error boundary (browser pass 7, turn 56e10c36).
 */
function diffEntries(diff: TurnDetailApplyDiff | null | undefined): TurnDetailApplyDiffEntry[] {
  if (!diff) return [];
  if (Array.isArray(diff)) return diff;
  return Object.entries(diff).map(([slot, moved]) => ({
    slot,
    before: moved?.before,
    after: moved?.after,
    reason: moved?.reason ?? null,
  }));
}

/**
 * The four readings APPLY can give a message (`turn/decide.py`), in the words an
 * operator reads the trace in.
 */
const DECISION_WORDS: Record<string, string> = {
  answer: 'Answered the open question',
  refine: 'Narrowed the subject',
  new_ask: 'Asked something new',
  carry: 'Ran as itself, question left open',
};

function decisionWords(kind: string): string {
  return DECISION_WORDS[kind] ?? kind;
}

function ApplySection({ apply }: { apply: TurnDetail['apply'] }) {
  if (!apply) return <Empty>Not recorded on this turn (APPLY shipped in S3).</Empty>;
  const stateDiff = diffEntries(apply.state_diff);
  const narrowing = apply.narrowing ?? [];
  return (
    <div className="space-y-3 text-xs">
      <div>
        <div className="mb-1 font-medium text-muted-foreground">Decision</div>
        {apply.decision ? (
          <p>
            <span className="font-medium">{decisionWords(apply.decision.kind)}</span>{' '}
            <span className="text-muted-foreground">{apply.decision.why}</span>
          </p>
        ) : (
          <Empty>Not recorded on this turn.</Empty>
        )}
      </div>
      {apply.verdict && (
        <div>
          <div className="mb-1 font-medium text-muted-foreground">Verdict</div>
          <Code value={apply.verdict} />
        </div>
      )}
      <div>
        <div className="mb-1 font-medium text-muted-foreground">State diff</div>
        {stateDiff.length === 0 ? (
          <Empty>Nothing changed this turn.</Empty>
        ) : (
          <ul className="space-y-1.5">
            {stateDiff.map((d, i) => (
              <li key={`${d.slot}-${i}`} className="rounded-md border px-2 py-1.5">
                <span className="font-medium">{d.slot}</span>{' '}
                <span className="text-muted-foreground">
                  {JSON.stringify(d.before)} {'->'} {JSON.stringify(d.after)}
                </span>
                {d.reason && <p className="mt-0.5 text-muted-foreground">{d.reason}</p>}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <div className="mb-1 font-medium text-muted-foreground">Narrowing applied</div>
        {narrowing.length === 0 ? (
          <Empty>No narrowing rule fired.</Empty>
        ) : (
          <ul className="space-y-1 text-muted-foreground">
            {narrowing.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <div className="mb-1 font-medium text-muted-foreground">Reconciliation</div>
        <p className="text-muted-foreground">{apply.reconciliation ?? 'Nothing to reconcile.'}</p>
      </div>
      <div>
        <div className="mb-1 font-medium text-muted-foreground">Turn plan</div>
        {typeof apply.plan === 'string' || !apply.plan ? (
          <p className="text-muted-foreground">{apply.plan ?? '-'}</p>
        ) : (
          <Code value={apply.plan} />
        )}
      </div>
      {apply.prompt_text && (
        <Collapsible>
          <CollapsibleTrigger className="text-primary underline-offset-2 hover:underline">
            Prompt text sent to the parser
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="mt-1 overflow-x-auto">
              <SearchableCode text={apply.prompt_text} />
            </div>
          </CollapsibleContent>
        </Collapsible>
      )}
    </div>
  );
}

/**
 * The current subject, from `focus.after` (chatbot memory lane A, contract section 6).
 * The backend has not fixed a shape for it - the mockup's sample joins a few plain
 * fields with " · " ("stock · SRTWB1455 · Kuching") - so an object is
 * rendered the same way, a string as itself, and nothing at all as absent.
 */
function currentSubjectText(after: unknown): string | null {
  if (after == null) return null;
  if (typeof after === 'string') return after || null;
  if (typeof after === 'object') {
    const parts = Object.values(after as Record<string, unknown>).filter(
      (v): v is string | number => typeof v === 'string' || typeof v === 'number',
    );
    return parts.length ? parts.join(' · ') : null;
  }
  return String(after);
}

function MemorySection({ memory }: { memory: TurnDetail['memory'] }) {
  if (!memory) return <Empty>Not recorded on this turn.</Empty>;
  const ownSet = memory.level.own != null;
  const subject = currentSubjectText(memory.focus?.after);
  const written = memory.episodes.written;
  const factsSaved = memory.facts_saved ?? [];

  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-2.5 gap-y-1.5 text-xs">
      <dt className="text-muted-foreground">Context level</dt>
      <dd>
        {memory.level.effective}{' '}
        <Badge variant="secondary" appearance="light" size="sm" className="ms-1">
          {ownSet ? 'own level' : 'system default'}
        </Badge>
      </dd>
      <dt className="text-muted-foreground">Current subject</dt>
      <dd className="text-muted-foreground">{subject ?? 'Not recorded on this turn.'}</dd>
      <dt className="text-muted-foreground">Conversation closed</dt>
      <dd className="text-muted-foreground">{written ? written.summary : 'none this turn'}</dd>
      <dt className="text-muted-foreground">Facts saved</dt>
      <dd className="text-muted-foreground">
        {factsSaved.length === 0
          ? 'none this turn'
          : factsSaved.map((f) => `${f.key} (${f.source})`).join(', ')}
      </dd>
    </dl>
  );
}

/**
 * "Context sent to the AI" (chatbot memory lane A, contract section 6's `context`
 * trace event) - each layer's estimated tokens against its own cap, and the total
 * against the turn cap.
 */
const CONTEXT_LAYER_LABEL: Record<string, string> = {
  L3: 'This conversation',
  L4: 'Past conversations',
  L5: 'About this contact',
  current_subject: 'Current subject',
  current_message: 'Current message',
};

function layerLabel(layer: TurnDetailContextLayer): string {
  return CONTEXT_LAYER_LABEL[layer.layer] ?? layer.layer;
}

function layerDropped(layer: TurnDetailContextLayer): string[] {
  if (Array.isArray(layer.dropped)) return layer.dropped;
  return layer.dropped ? [layerLabel(layer)] : [];
}

function ContextSection({ context }: { context: TurnDetail['context'] }) {
  if (!context) return <Empty>Not recorded on this turn.</Empty>;
  const dropped = context.layers.flatMap(layerDropped);
  return (
    <div className="space-y-2 text-xs">
      {context.layers.map((layer, i) => {
        const pct = layer.cap > 0 ? Math.min(100, (layer.est_tokens / layer.cap) * 100) : 0;
        return (
          <div key={`${layer.layer}-${i}`} className="flex items-center gap-2">
            <span className="w-36 shrink-0 truncate text-muted-foreground" title={layerLabel(layer)}>
              {layerLabel(layer)}
            </span>
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
              <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
            </div>
            <span className="w-20 shrink-0 text-end tabular-nums text-muted-foreground">
              {layer.est_tokens} / {layer.cap}
            </span>
          </div>
        );
      })}
      <div className="flex items-center gap-2 font-medium">
        <span className="w-36 shrink-0">Total memory + message</span>
        <div className="flex-1" />
        <span className="w-20 shrink-0 text-end tabular-nums">
          {context.total_est_tokens} / {context.cap}
        </span>
      </div>
      <p className="text-muted-foreground">
        Dropped: {dropped.length === 0 ? 'nothing' : dropped.join(', ')}
      </p>
    </div>
  );
}

/**
 * The per-contact ordering ticket (chatbot memory lane A, contract section 6's `order`
 * trace event) - read-only, nothing to set.
 */
function orderNeighborText(neighbor: TurnDetailOrderNeighbor): string {
  return `${formatDateTimeInMalaysia(neighbor.created_at)} "${neighbor.message}"`;
}

function OrderSection({ order }: { order: TurnDetail['order'] }) {
  if (!order) return <Empty>Not recorded on this turn.</Empty>;
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-2.5 gap-y-1.5 text-xs">
      <dt className="text-muted-foreground">Place in line</dt>
      <dd>#{order.ticket} for this contact</dd>
      <dt className="text-muted-foreground">Waited</dt>
      <dd>{(order.waited_ms / 1000).toFixed(1)} s</dd>
      <dt className="text-muted-foreground">Ran after</dt>
      <dd className="text-muted-foreground">
        {order.previous ? orderNeighborText(order.previous) : 'Not recorded on this turn.'}
      </dd>
      <dt className="text-muted-foreground">Next</dt>
      <dd className="text-muted-foreground">
        {order.next ? orderNeighborText(order.next) : 'Not recorded on this turn.'}
      </dd>
    </dl>
  );
}

function DecaySection({ decay }: { decay: TurnDetailDecay[] }) {
  if (decay.length === 0) return <Empty>Nothing decayed this turn.</Empty>;
  return (
    <ul className="space-y-2 text-xs">
      {decay.map((d, i) => (
        <li key={`${d.slot}-${i}`} className="rounded-md border px-2 py-1.5">
          <div className="flex items-center gap-2">
            <span className="font-medium">{d.slot}</span>
            {d.age_turns != null && (
              <span className="text-muted-foreground">{d.age_turns} turns old</span>
            )}
          </div>
          {d.reason && <p className="text-muted-foreground">{d.reason}</p>}
        </li>
      ))}
    </ul>
  );
}

function OpenQuestionSection({
  openQuestion,
}: {
  openQuestion: TurnDetail['open_question'];
}) {
  if (!openQuestion) return <Empty>No open question this turn.</Empty>;
  return (
    <div className="space-y-2 text-xs">
      <dl className="grid grid-cols-[auto_1fr] gap-x-2.5 gap-y-0.5">
        <dt className="text-muted-foreground">handler</dt>
        <dd>{openQuestion.handler ?? '-'}</dd>
        <dt className="text-muted-foreground">outcome</dt>
        <dd>{openQuestion.outcome ?? '-'}</dd>
      </dl>
      <Code value={{ before: openQuestion.before, answer: openQuestion.answer, after: openQuestion.after }} />
    </div>
  );
}

function FocusSection({ focus }: { focus: TurnDetailFocus[] }) {
  if (focus.length === 0) return <Empty>No focus rule fired this turn.</Empty>;
  return (
    <ul className="space-y-2 text-xs">
      {focus.map((f, i) => (
        <li key={`${f.slot}-${i}`} className="rounded-md border px-2 py-1.5">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium">{f.slot}</span>
            <Badge variant="secondary" appearance="light" size="sm">
              {f.rule}
            </Badge>
            {f.source && (
              <span className="text-2xs text-muted-foreground">source: {f.source}</span>
            )}
          </div>
          <div className="mt-1 text-muted-foreground">
            {JSON.stringify(f.before)} {'->'} {JSON.stringify(f.after)}
          </div>
        </li>
      ))}
    </ul>
  );
}

function ToolSection({ tool }: { tool: TurnDetail['tool'] }) {
  if (!tool) return <Empty>No tool call recorded.</Empty>;
  return (
    <div className="space-y-2 text-xs">
      <dl className="grid grid-cols-[auto_1fr] gap-x-2.5 gap-y-0.5">
        <dt className="text-muted-foreground">name</dt>
        <dd>{tool.name ?? '-'}</dd>
        <dt className="text-muted-foreground">ms</dt>
        <dd>{tool.ms ?? '-'}</dd>
      </dl>
      {tool.args && (
        <div>
          <div className="mb-1 font-medium text-muted-foreground">Args</div>
          <Code value={tool.args} />
        </div>
      )}
      {tool.envelope && (
        <div>
          <div className="mb-1 font-medium text-muted-foreground">Envelope</div>
          <Code value={tool.envelope} />
        </div>
      )}
    </div>
  );
}

function CrossdomainSection({ crossdomain }: { crossdomain: TurnDetailCrossdomain[] }) {
  if (crossdomain.length === 0) return <Empty>No cross-domain probe this turn.</Empty>;
  return (
    <ul className="space-y-2 text-xs">
      {crossdomain.map((c, i) => (
        <li key={`${c.tool}-${i}`} className="rounded-md border px-2 py-1.5">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant="secondary" appearance="light" size="sm">
              rung {c.rung}
            </Badge>
            <span className="font-medium">{c.tool}</span>
            <span className="text-muted-foreground">{c.rows ?? 0} rows</span>
            {c.rendered ? (
              <Badge variant="success" appearance="light" size="sm">
                rendered
              </Badge>
            ) : (
              <Badge variant="secondary" appearance="light" size="sm">
                not rendered
              </Badge>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}

function RevealsSection({ reveals }: { reveals: TurnDetail['reveals'] }) {
  const seen = reveals.restricted_fields_seen.length > 0;
  if (!seen) return <Empty>No restricted field was on this answer.</Empty>;
  return (
    <div className="space-y-2 text-xs">
      <ChipRow label="Seen" chips={reveals.restricted_fields_seen} tone="secondary" />
      <ChipRow label="Granted" chips={reveals.granted} tone="success" />
      <ChipRow label="Dropped" chips={reveals.dropped} tone="destructive" />
    </div>
  );
}

function SessionSection({ session }: { session: TurnDetail['session'] }) {
  const gained = session.diff.filter((d) => d.change === 'gained').map((d) => d.key);
  const lost = session.diff.filter((d) => d.change === 'lost').map((d) => d.key);
  return (
    <div className="space-y-2 text-xs">
      <div className="grid grid-cols-2 gap-3">
        <ChipRow label="Lost" chips={lost} tone="destructive" />
        <ChipRow label="Gained" chips={gained} tone="success" />
      </div>
      <div>
        <div className="mb-1 font-medium text-muted-foreground">Before / after</div>
        <Code value={{ before: session.before, after: session.after }} />
      </div>
    </div>
  );
}

function ChipRow({
  label,
  chips,
  tone,
}: {
  label: string;
  chips: string[];
  tone: BadgeProps['variant'];
}) {
  return (
    <div>
      <div className="mb-1 text-2xs font-medium text-muted-foreground">{label}</div>
      {chips.length === 0 ? (
        <span className="text-2xs text-muted-foreground/70">none</span>
      ) : (
        <div className="flex flex-wrap gap-1">
          {chips.map((c) => (
            <Badge key={c} variant={tone} appearance="light" size="sm">
              {c}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}
