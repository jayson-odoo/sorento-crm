'use client';

import { Badge } from '@/components/ui/badge';
import { Popover, PopoverContent, PopoverPortal, PopoverTrigger } from '@/components/ui/popover';
import { EM_DASH } from '../../lib/format';
import {
  describeLevelSuggestion,
  levelActionLabel,
  type LevelSuggestion,
} from '../lib/levelSuggestion';

/**
 * The third suggestion on a plan row (S13f): the reorder level to set back in AutoCount.
 *
 * > "the third suggestion is I should suggest the reorder level"
 *
 * Always an ASK. The engine writes only the suggestion; the stored level is the buyer's
 * and the change happens in AutoCount, by them. So the cell says "Set AutoCount level to
 * 24, now 20" and the popup shows the sums - it never implies anything already moved.
 */
export function PlanLevelCell({ suggestion }: { suggestion: LevelSuggestion | undefined }) {
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
        <PopoverContent className="w-80 text-xs" align="start">
          <p className="font-medium text-foreground">{describeLevelSuggestion(suggestion)}</p>
          {/* The limit, stated where the advice is given, same as the price popup. */}
          <p className="mt-3 border-t pt-2 text-2xs text-muted-foreground">
            Based on our own outgoing orders only. Applying it happens in AutoCount.
          </p>
        </PopoverContent>
      </PopoverPortal>
    </Popover>
  );
}
