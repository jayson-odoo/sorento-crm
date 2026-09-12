'use client';

import { useMemo, useState } from 'react';
import { Activity, ChevronDown, ChevronRight } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { SearchableCode } from '@/components/common/find-in-text/SearchableCode';
import { cn } from '@/lib/utils';
import { deriveStateSummary } from '../stateTrace';
import type { StateTrace } from '../types/chatHistory.types';

/**
 * Per-incoming-message state-transition inspector for the transcript drawer.
 *
 * Collapsed by default: shows a one-line signal (version, lost-entity count, whether the
 * turn wrote state) so a scan surfaces the suspicious turns without opening every row.
 * Expanded: the derived summary (entities lost/gained, cause flags, parser drift - 
 * mirroring `v_turn_state_transition`) plus the raw jsonb in a searchable viewer
 * (Cmd/Ctrl+F), the same pattern as the AI-assistant trace inspector.
 */
export function StateTracePanel({
  trace,
  shadow = null,
}: {
  trace: StateTrace;
  /**
   * AC-1029. The SHADOW parse of the same message, when the Shadow filter is on and a
   * shadow row exists. Given the same shape as `trace`, so both columns of the Parser
   * drift row are derived by `deriveStateSummary` rather than by two different rules.
   */
  shadow?: StateTrace | null;
}) {
  const [open, setOpen] = useState(false);
  const summary = useMemo(() => deriveStateSummary(trace), [trace]);
  const shadowSummary = useMemo(() => deriveStateSummary(shadow), [shadow]);
  const raw = useMemo(() => JSON.stringify(trace, null, 2), [trace]);

  if (!summary) return null;

  const lostCount = summary.entitiesLost?.length ?? 0;
  const hasLoss = lostCount > 0;

  return (
    <div className="mt-2 border-t pt-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 text-[11px] text-muted-foreground hover:text-foreground transition-colors"
        aria-expanded={open}
      >
        {open ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
        <Activity className="size-3.5" />
        <span>state trace</span>
        <span className="text-muted-foreground/70">v{summary.traceVersion}</span>
        {!summary.wroteState && (
          <Badge variant="secondary" className="ml-1 h-4 px-1 text-[10px]">
            no state written
          </Badge>
        )}
        {hasLoss && (
          <Badge variant="destructive" className="ml-1 h-4 px-1 text-[10px]">
            {lostCount} lost
          </Badge>
        )}
      </button>

      {open && (
        <div className="mt-2 space-y-2">
          <ChipRow label="Lost" chips={summary.entitiesLost} tone="destructive" emptyIsNull />
          <ChipRow label="Gained" chips={summary.entitiesGained} tone="success" emptyIsNull />
          <ChipRow label="Flags" chips={summary.causeFlags} tone="secondary" />
          {/* AC-1029: two columns once a shadow parse exists, so "what post-processing
              changed" can be read for the live version and the one being trialled without
              opening two screens. One column when nothing is shadowing this turn - an
              empty second column would read as "the shadow found nothing". */}
          {shadow ? (
            <Row label="Parser drift">
              <div className="grid grid-cols-2 gap-2" data-testid="parser-drift-columns">
                <DriftColumn title="live" chips={summary.parserDrift} />
                <DriftColumn title="shadow" chips={shadowSummary?.parserDrift ?? null} />
              </div>
            </Row>
          ) : (
            <ChipRow label="Parser drift" chips={summary.parserDrift} tone="warning" nullMeans="raw not captured" />
          )}
          <div>
            <div className="text-[11px] font-medium text-muted-foreground mb-1">Raw trace</div>
            <SearchableCode
              text={raw}
              ariaLabel="Raw state trace (press Cmd/Ctrl+F to search)"
              data-testid="state-trace-raw"
            />
          </div>
        </div>
      )}
    </div>
  );
}

/** One side of the two-column Parser drift row. Same chips, said per version. */
function DriftColumn({ title, chips }: { title: string; chips: string[] | null }) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground/70">{title}</div>
      {chips === null ? (
        <span className="text-[11px] italic text-muted-foreground/70">
          {title === 'shadow' ? 'no shadow parse' : 'raw not captured'}
        </span>
      ) : chips.length === 0 ? (
        <span className="text-[11px] text-muted-foreground/70">none</span>
      ) : (
        <div className="flex flex-wrap gap-1">
          {chips.map((c) => (
            <Badge key={c} variant="warning" className="h-4 px-1 text-[10px] font-normal">
              {c}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}

function ChipRow({
  label,
  chips,
  tone,
  emptyIsNull = false,
  nullMeans,
}: {
  label: string;
  chips: string[] | null;
  tone: 'destructive' | 'success' | 'secondary' | 'warning';
  /** When true, an empty [] (as opposed to null) renders "none" rather than being hidden. */
  emptyIsNull?: boolean;
  /** Text shown when the value is null (distinct from empty). */
  nullMeans?: string;
}) {
  // null carries meaning: "turn wrote no state" (entities) / "parser_raw absent" (drift).
  // It is NOT the same as an empty set, so we render it distinctly rather than hiding.
  if (chips === null) {
    return (
      <Row label={label}>
        <span className="text-[11px] italic text-muted-foreground/70">
          {nullMeans ?? 'n/a - turn wrote no state'}
        </span>
      </Row>
    );
  }
  if (chips.length === 0) {
    return (
      <Row label={label}>
        <span className="text-[11px] text-muted-foreground/70">{emptyIsNull ? 'none' : '-'}</span>
      </Row>
    );
  }
  return (
    <Row label={label}>
      <div className="flex flex-wrap gap-1">
        {chips.map((c) => (
          <Badge key={c} variant={tone as never} className={cn('h-4 px-1 text-[10px] font-normal')}>
            {c}
          </Badge>
        ))}
      </div>
    </Row>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2">
      <span className="text-[11px] font-medium text-muted-foreground w-20 shrink-0 pt-0.5">
        {label}
      </span>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
