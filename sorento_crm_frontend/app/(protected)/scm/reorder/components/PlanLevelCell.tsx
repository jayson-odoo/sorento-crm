'use client';

import { useState } from 'react';
import dynamic from 'next/dynamic';
import type { ApexOptions } from 'apexcharts';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { EM_DASH } from '../../lib/format';
import {
  describeLevelSuggestion,
  effectiveLevel,
  levelActionLabel,
  levelTerms,
  quantityActionLabel,
  type LevelSuggestion,
} from '../lib/levelSuggestion';

const ApexChart = dynamic(() => import('react-apexcharts').then((mod) => mod.default), {
  ssr: false,
});

/**
 * The third suggestion on a plan row (S13f/S14): the reorder level to set in AutoCount.
 *
 * > "the third suggestion is I should suggest the reorder level"
 * > "need to explain how you reach the recommendation, and allow for amendments"
 *
 * Always an ASK. The engine writes only the suggestion; the stored level is the buyer's
 * and the change happens in AutoCount, by them. The popup carries the full derivation -
 * the three terms the level is made of (ADU a day, the lead time, the safety stock) and
 * the months behind the average - and a field to put the buyer's own figure beside the
 * engine's. An amendment never hides the engine's number: "you set 30; engine said 24"
 * stays on the row.
 */
export function PlanLevelCell({
  suggestion,
  onAmend,
}: {
  suggestion: LevelSuggestion | undefined;
  /** Record (or withdraw, with null) the buyer's own figure. Absent = read-only. */
  onAmend?: (s: LevelSuggestion, amended: number | null) => Promise<void> | void;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // No opinion renders as absence: "we did not compute one" and "keep it" are different
  // answers, and a placeholder number would be the engine deciding by accident.
  if (!suggestion) {
    return (
      <span className="text-muted-foreground" title="No level suggestion for this item">
        {EM_DASH}
      </span>
    );
  }

  const action = levelActionLabel(suggestion);
  const amended =
    suggestion.amended_level !== null &&
    suggestion.amended_level !== suggestion.suggested_level;
  const months = suggestion.basis.months ?? [];

  const save = async () => {
    if (!onAmend || draft === null) return;
    const parsed = draft.trim() === '' ? null : Number(draft);
    if (parsed !== null && (!Number.isFinite(parsed) || parsed < 0)) return;
    // Typing the engine's own number back is a withdrawal, not an amendment.
    const next = parsed === suggestion.suggested_level ? null : parsed;
    setSaving(true);
    try {
      await onAmend(suggestion, next);
      setDraft(null);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button type="button" className="min-w-0 text-left" aria-label="Level suggestion">
          <Badge
            variant={action.changed ? 'info' : 'success'}
            appearance="light"
            size="sm"
          >
            {action.label}
          </Badge>
          <span className="mt-0.5 block truncate text-2xs text-muted-foreground">
            {action.detail}
          </span>
          {/* The second half of the AutoCount pair: the qty to order when the level
              fires. Result on the row; its arithmetic stays in the popup. */}
          {quantityActionLabel(suggestion) ? (
            <span className="block truncate text-2xs text-muted-foreground">
              {quantityActionLabel(suggestion)}
            </span>
          ) : null}
        </button>
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent className="w-96 text-xs" align="start">
          <p className="font-medium text-foreground">{describeLevelSuggestion(suggestion)}</p>

          {/* The three terms, each with its own figure: a level nobody can take apart is
              a level nobody argues with, and the sentence above is prose either way. */}
          <div className="mt-2 grid grid-cols-3 gap-2 border-t pt-2 text-2xs">
            {levelTerms(suggestion).map((t) => (
              <div key={t.label}>
                <p className="text-muted-foreground">{t.label}</p>
                <p className="tabular-nums font-medium text-foreground">{t.value}</p>
              </div>
            ))}
          </div>

          {/* The months behind the average, as bars with the exact figure on each, so
              the arithmetic can be checked at a glance rather than taken on faith
              (user markup, 2026-08-11: the level needs a drill-down explanation). */}
          {months.length ? (
            <div className="mt-1 -mx-1">
              <ApexChart
                options={{
                  chart: { type: 'bar', toolbar: { show: false }, sparkline: { enabled: false } },
                  plotOptions: { bar: { columnWidth: '55%', borderRadius: 2 } },
                  colors: ['var(--color-primary, #2563eb)'],
                  dataLabels: { enabled: true, style: { fontSize: '10px' } },
                  xaxis: {
                    categories: months.map((m) => m.month),
                    labels: { style: { fontSize: '10px' } },
                  },
                  yaxis: { labels: { show: false } },
                  grid: { show: false },
                  tooltip: { enabled: false },
                } satisfies ApexOptions}
                series={[{ name: 'Left this location', data: months.map((m) => m.qty) }]}
                type="bar"
                height={110}
              />
            </div>
          ) : null}

          {/* The buyer's own figure, beside the engine's - never instead of it. */}
          {onAmend ? (
            <div className="mt-3 flex items-center gap-2 border-t pt-3">
              <span className="shrink-0 text-muted-foreground">Set instead to</span>
              <Input
                type="number"
                min={0}
                inputMode="decimal"
                className="h-7 w-24"
                aria-label="Your level"
                value={draft ?? String(effectiveLevel(suggestion))}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') void save();
                }}
              />
              <Button size="sm" variant="outline" disabled={saving || draft === null} onClick={() => void save()}>
                Save
              </Button>
              {amended ? (
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={saving}
                  onClick={async () => {
                    setSaving(true);
                    try {
                      await onAmend(suggestion, null);
                      setDraft(null);
                    } finally {
                      setSaving(false);
                    }
                  }}
                >
                  Use engine&apos;s {suggestion.suggested_level}
                </Button>
              ) : null}
            </div>
          ) : null}

          {/* The limit, stated where the advice is given, same as the price popup. */}
          <p className="mt-3 border-t pt-2 text-2xs text-muted-foreground">
            Based on our own outgoing orders only. Applying it happens in AutoCount.
          </p>
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}
