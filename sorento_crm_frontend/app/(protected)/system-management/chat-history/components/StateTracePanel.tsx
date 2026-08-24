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
 * Expanded: the derived summary (entities lost/gained, cause flags, parser drift  - 
 * mirroring `v_turn_state_transition`) plus the raw jsonb in a searchable viewer
 * (Cmd/Ctrl+F), the same pattern as the AI-assistant trace inspector.
 */
export function StateTracePanel({ trace }: { trace: StateTrace }) {
  const [open, setOpen] = useState(false);
  const summary = useMemo(() => deriveStateSummary(trace), [trace]);
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
          <ChipRow label="Parser drift" chips={summary.parserDrift} tone="warning" nullMeans="raw not captured" />
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
