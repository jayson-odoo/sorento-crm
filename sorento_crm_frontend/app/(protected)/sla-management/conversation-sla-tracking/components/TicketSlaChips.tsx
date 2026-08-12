'use client';

import { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, Clock, TrendingUp } from 'lucide-react';

import { formatDateTimeInMalaysia, parseDateTimeAsUTC } from '@/lib/helpers';

const TICK_MS = 30_000;
/** Under this much time left a countdown reads as at-risk (amber). */
const AT_RISK_MS = 15 * 60_000;

interface TicketSlaChipsProps {
  dueAt: string | null;
  dueAtResolution: string | null;
  isResponded: boolean;
  respondedAt?: string | null;
  currentTier: number;
  /** Stamped only by a real escalation - a high tier alone is not escalated. */
  escalatedAt?: string | null;
  className?: string;
}

/** "in 46m" / "in 5h 50m" / "22m overdue" - one clock, read at a glance. */
function countdownLabel(due: string, nowMs: number): { text: string; msLeft: number } {
  const msLeft = parseDateTimeAsUTC(due).getTime() - nowMs;
  const abs = Math.abs(msLeft);
  const mins = Math.floor(abs / 60_000);
  const hours = Math.floor(mins / 60);
  const days = Math.floor(hours / 24);
  let magnitude: string;
  if (days >= 1) magnitude = `${days}d ${hours % 24}h`;
  else if (hours >= 1) magnitude = `${hours}h ${mins % 60}m`;
  else magnitude = `${Math.max(mins, 0)}m`;
  return { text: msLeft >= 0 ? `in ${magnitude}` : `${magnitude} overdue`, msLeft };
}

function chipClass(msLeft: number | null): string {
  if (msLeft == null) return 'border-border text-muted-foreground';
  if (msLeft < 0) return 'border-destructive/40 bg-destructive/10 text-destructive';
  if (msLeft < AT_RISK_MS)
    return 'border-amber-400/50 bg-amber-50 text-amber-700 dark:bg-amber-950/30 dark:text-amber-400';
  return 'border-border text-muted-foreground';
}

/**
 * The two clocks an intervention ticket races: first response, then resolution.
 * Shared by the worklist row and the ticket drawer header so they can never
 * disagree.
 */
export default function TicketSlaChips({
  dueAt,
  dueAtResolution,
  isResponded,
  respondedAt,
  currentTier,
  escalatedAt,
  className = '',
}: TicketSlaChipsProps) {
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    const t = setInterval(() => setNowMs(Date.now()), TICK_MS);
    return () => clearInterval(t);
  }, []);

  const respond = dueAt ? countdownLabel(dueAt, nowMs) : null;
  const resolve = dueAtResolution ? countdownLabel(dueAtResolution, nowMs) : null;

  const base =
    'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] leading-4';

  return (
    <div className={`flex flex-wrap items-center gap-1.5 ${className}`}>
      {isResponded ? (
        <span
          className={`${base} border-emerald-400/50 bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400`}
          title={respondedAt ? `Responded ${formatDateTimeInMalaysia(respondedAt)}` : 'Responded'}
        >
          <CheckCircle2 className="size-3" />
          Responded
        </span>
      ) : (
        <span
          className={`${base} ${chipClass(respond?.msLeft ?? null)}`}
          title={dueAt ? `Respond by ${formatDateTimeInMalaysia(dueAt)}` : 'No response deadline'}
        >
          <Clock className="size-3" />
          Respond {respond?.text ?? 'not set'}
        </span>
      )}

      <span
        className={`${base} ${chipClass(resolve?.msLeft ?? null)}`}
        title={
          dueAtResolution
            ? `Resolve by ${formatDateTimeInMalaysia(dueAtResolution)}`
            : 'No resolution deadline'
        }
      >
        <Clock className="size-3" />
        Resolve {resolve?.text ?? 'not set'}
      </span>

      <span className={`${base} border-border text-muted-foreground`}>Tier {currentTier}</span>

      {escalatedAt && (
        <span
          className={`${base} border-amber-400/50 bg-amber-50 text-amber-700 dark:bg-amber-950/30 dark:text-amber-400`}
          title={`Escalated ${formatDateTimeInMalaysia(escalatedAt)}`}
        >
          <TrendingUp className="size-3" />
          Escalated
        </span>
      )}

      {!isResponded && respond && respond.msLeft < 0 && (
        <span className="inline-flex items-center gap-1 text-[11px] text-destructive">
          <AlertTriangle className="size-3" />
          Response breached
        </span>
      )}
    </div>
  );
}
