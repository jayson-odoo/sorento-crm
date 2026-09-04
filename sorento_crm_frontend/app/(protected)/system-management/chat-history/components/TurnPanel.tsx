'use client';

import { useMemo, useState } from 'react';
import { Check, ChevronDown, ChevronRight, Copy, RotateCcw, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { SearchableCode } from '@/components/common/find-in-text/SearchableCode';
import { cn } from '@/lib/utils';
import { useRetryChatbotTurn } from '../hooks/useChatbotTurns';
import {
  buildTimeline,
  canRetry,
  formatMs,
  laneWords,
  memoryChips,
  rememberedRecord,
  shortTurnId,
  turnDuration,
  turnHeadline,
} from '../turnPresentation';
import type { ChatbotTurn, TurnTraceRecord } from '../types/chatbotTurn.types';

/**
 * The turn trace under one incoming message (AC-251 to AC-256).
 *
 * Replaces `StateTracePanel`, which showed the same turn as raw jsonb behind a toggle
 * labelled "state trace". The operator journey this serves is "the bot answered wrongly,
 * what did it do?", and the answer to that is sentences, in order, with the JSON kept
 * behind one more click for the engineer who needs it.
 *
 * Collapsed by default: a thread has many turns and the status line alone is what a scan
 * needs. Failed turns carry the destructive tone so they are findable without expanding.
 */
export function TurnPanel({ turn }: { turn: ChatbotTurn }) {
  const [open, setOpen] = useState(false);
  const headline = useMemo(() => turnHeadline(turn), [turn]);
  const rows = useMemo(() => buildTimeline(turn), [turn]);
  const duration = turnDuration(turn);
  const failed = headline.tone === 'failed';

  return (
    <div
      className={cn(
        'mt-2 rounded-lg border bg-background px-2.5 py-2',
        failed && 'border-destructive/40',
      )}
      data-testid="turn-panel"
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-1.5 flex-wrap text-start"
      >
        <Badge
          variant={failed ? 'destructive' : headline.tone === 'pending' ? 'warning' : 'success'}
          appearance="light"
          size="sm"
        >
          {headline.word}
        </Badge>
        {turn.branch_kind && laneWords(turn.branch_kind) !== headline.word && (
          // Two suppressions. On `clarify_menu` and friends the status word IS the lane,
          // and printing it twice reads as a rendering bug rather than as emphasis. On a
          // turn that failed before routing there is no lane at all, and "Failed at
          // Understood, Lane not reached" says the same thing twice in a worse voice -
          // the timeline's own "not reached" row already carries it.
          <span className="text-xs text-muted-foreground">{laneWords(turn.branch_kind)}</span>
        )}
        {turn.attempt > 1 && (
          <Badge variant="warning" appearance="light" size="sm">
            attempt {turn.attempt}
          </Badge>
        )}
        {turn.duplicate && (
          <Badge variant="secondary" appearance="light" size="sm">
            repeat delivery
          </Badge>
        )}
        {turn.is_test && (
          <Badge variant="secondary" appearance="light" size="sm">
            test
          </Badge>
        )}
        {duration && (
          <span className="text-xs text-muted-foreground tabular-nums">{duration}</span>
        )}
        <span className="ms-auto flex items-center gap-1 text-xs text-muted-foreground">
          {open ? 'hide' : 'details'}
          {open ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
        </span>
      </button>

      {open && (
        <div className="mt-2">
          <ol className="ms-1.5 border-s ps-0 space-y-0">
            {rows.map((row, i) =>
              row.kind === 'stage' ? (
                <StageRow key={`${row.record.stage}-${i}`} record={row.record} label={row.label} turn={turn} />
              ) : (
                <NotReachedRow key={`skipped-${i}`} labels={row.labels} />
              ),
            )}
          </ol>
          <TurnFooter turn={turn} />
        </div>
      )}
    </div>
  );
}

function Dot({ tone }: { tone: 'ok' | 'failed' | 'skipped' }) {
  return (
    <span
      aria-hidden
      className={cn(
        'absolute -start-[5px] top-2 size-2.5 rounded-full ring-2 ring-background',
        tone === 'failed' && 'bg-destructive',
        tone === 'ok' && 'bg-[var(--color-success-accent,var(--color-green-500))]',
        tone === 'skipped' && 'bg-muted-foreground/40',
      )}
    />
  );
}

function StageRow({
  record,
  label,
  turn,
}: {
  record: TurnTraceRecord;
  label: string;
  turn: ChatbotTurn;
}) {
  const failed = record.status === 'failed';
  const memory = record.stage === 'remembered' ? memoryChips(rememberedRecord(turn)) : [];

  return (
    <li className="relative ps-4 pb-2.5">
      <Dot tone={failed ? 'failed' : 'ok'} />
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-medium">{label}</span>
        <span className="text-2xs text-muted-foreground tabular-nums shrink-0">
          {formatMs(record.ms)}
        </span>
      </div>

      {failed && record.error ? (
        <p className="mt-1 rounded-md border border-destructive/30 bg-destructive/5 px-2 py-1.5 text-xs text-destructive">
          {record.error}
        </p>
      ) : (
        <p className="text-xs text-muted-foreground">{record.summary}</p>
      )}
      {record.why && !failed && (
        <p className="text-2xs italic text-muted-foreground/80">{record.why}</p>
      )}

      {Object.keys(record.facts ?? {}).length > 0 && (
        <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-2.5 gap-y-0.5 text-2xs">
          {Object.entries(record.facts).map(([key, value]) => (
            <div key={key} className="contents">
              <dt className="text-muted-foreground">{key.replace(/_/g, ' ')}</dt>
              <dd className="min-w-0 truncate" title={String(value)}>
                {String(value)}
              </dd>
            </div>
          ))}
        </dl>
      )}

      {record.stage === 'remembered' && <MemoryChips chips={memory} />}
      {failed && <FailedStageActions turn={turn} />}
    </li>
  );
}

/**
 * AC-252 / mockup. One row for everything the failure stopped, rather than a greyed
 * placeholder per stage. On a failed turn the operator needs to know the rest did not run
 * ("memory unchanged" is the follow-up question); eight grey rows would bury that.
 */
function NotReachedRow({ labels }: { labels: string[] }) {
  return (
    <li className="relative ps-4 pb-2.5">
      <Dot tone="skipped" />
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-medium text-muted-foreground">{labels.join(' · ')}</span>
        <span className="text-2xs text-muted-foreground shrink-0">not reached</span>
      </div>
      <p className="text-xs text-muted-foreground">Memory was left unchanged.</p>
    </li>
  );
}

/** AC-254. Labels, with the session-vars key in the tooltip. */
function MemoryChips({ chips }: { chips: ReturnType<typeof memoryChips> }) {
  if (chips.length === 0) return null;
  const tone = { kept: 'success', new: 'info', cleared: 'warning' } as const;
  return (
    <div className="mt-1.5 flex flex-wrap gap-1">
      {chips.map((chip) => (
        <Badge
          key={`${chip.kind}-${chip.rawKey}`}
          variant={tone[chip.kind]}
          appearance="light"
          size="sm"
          title={chip.rawKey}
        >
          {chip.kind} · {chip.label}
        </Badge>
      ))}
    </div>
  );
}

/** AC-253. Retry is enabled only on a failed turn; R4 says this is the only retry there is. */
function FailedStageActions({ turn }: { turn: ChatbotTurn }) {
  const retry = useRetryChatbotTurn();
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      <Button
        size="sm"
        variant="primary"
        disabled={!canRetry(turn) || retry.isPending}
        onClick={() => retry.mutate(turn.id)}
      >
        <RotateCcw className="size-3.5" />
        {retry.isPending ? 'Re-queueing' : 'Retry turn'}
      </Button>
      <CopyTurnId id={turn.id} />
    </div>
  );
}

/** The full id is copyable; only the short handle is ever displayed (no bare UUIDs). */
function CopyTurnId({ id }: { id: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      size="sm"
      variant="outline"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(id);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          setCopied(false);
        }
      }}
      title={`Copy turn ${shortTurnId(id)}`}
    >
      {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
      {copied ? 'Copied' : `Turn ${shortTurnId(id)}`}
    </Button>
  );
}

/** AC-253's technical half: every stage's raw payload, in the existing searchable viewer. */
function TurnFooter({ turn }: { turn: ChatbotTurn }) {
  const [showRaw, setShowRaw] = useState(false);
  const raw = useMemo(
    () =>
      JSON.stringify(
        turn.trace.map((r) => ({ stage: r.stage, status: r.status, ms: r.ms, raw: r.raw })),
        null,
        2,
      ),
    [turn.trace],
  );

  return (
    <div className="mt-1 border-t pt-2">
      <div className="flex items-center gap-2 flex-wrap">
        <button
          type="button"
          onClick={() => setShowRaw((v) => !v)}
          aria-expanded={showRaw}
          className="flex items-center gap-1 text-2xs text-muted-foreground hover:text-foreground transition-colors"
        >
          {showRaw ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
          Technical details
        </button>
        {showRaw && (
          <Button
            size="sm"
            variant="ghost"
            className="h-6 px-1.5 ms-auto"
            onClick={() => setShowRaw(false)}
            aria-label="Hide technical details"
          >
            <X className="size-3.5" />
          </Button>
        )}
      </div>
      {showRaw && (
        <div className="mt-1.5">
          <SearchableCode
            text={raw}
            ariaLabel="Raw turn payloads (press Cmd/Ctrl+F to search)"
            data-testid="turn-raw"
          />
        </div>
      )}
    </div>
  );
}
