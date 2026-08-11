'use client';

import { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { EM_DASH } from '../../lib/format';
import {
  describeLevelSuggestion,
  effectiveLevel,
  levelActionLabel,
  type LevelSuggestion,
} from '../lib/levelSuggestion';

/**
 * The third suggestion on a plan row (S13f/S14): the reorder level to set in AutoCount.
 *
 * > "the third suggestion is I should suggest the reorder level"
 * > "need to explain how you reach the recommendation, and allow for amendments"
 *
 * Always an ASK. The engine writes only the suggestion; the stored level is the buyer's
 * and the change happens in AutoCount, by them. The popup carries the full derivation -
 * the months studied, the average, the cover, the trend that leaned the rounding - and a
 * field to put the buyer's own figure beside the engine's. An amendment never hides the
 * engine's number: "you set 30; engine said 24" stays on the row.
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
        </button>
      </PopoverTrigger>
      <PopoverPortal>
        <PopoverContent className="w-96 text-xs" align="start">
          <p className="font-medium text-foreground">{describeLevelSuggestion(suggestion)}</p>

          {/* The months behind the average, so the arithmetic can be checked line by
              line rather than taken on faith. */}
          {months.length ? (
            <table className="mt-2 w-full">
              <tbody>
                <tr className="text-muted-foreground">
                  {months.map((m) => (
                    <td key={m.month} className="pr-2 text-2xs">
                      {m.month}
                    </td>
                  ))}
                </tr>
                <tr className="font-medium tabular-nums">
                  {months.map((m) => (
                    <td key={m.month} className="pr-2">
                      {m.qty}
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
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
