'use client';

import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';

/** `all` is only reached from a link (`?scope=all`): no segment pressed, every line shown. */
export type BoardScope = 'saved' | 'others' | 'all';

/**
 * Saved | Others, the quick check of what Confirm will send against everything else. The design
 * system's own segmented control (`components/ui/toggle-group.tsx`, single select, outline, `sm`
 * = the 28 px height of the toolbar buttons beside it), never a hand-rolled pair of buttons.
 * A single-select Radix group reports an empty value when the pressed segment is pressed again;
 * that is ignored so one segment is always on.
 */
export function BoardScopeToggle({
  value,
  onChange,
  savedCount,
  othersCount,
}: {
  value: BoardScope;
  onChange: (next: BoardScope) => void;
  savedCount: number;
  othersCount: number;
}) {
  return (
    <ToggleGroup
      type="single"
      variant="outline"
      size="sm"
      value={value === 'all' ? '' : value}
      onValueChange={(next) => {
        if (next === 'saved' || next === 'others') onChange(next);
      }}
      aria-label="Saved or others"
      data-testid="board-scope-toggle"
    >
      <ToggleGroupItem value="saved" aria-label={`Saved (${savedCount})`}>
        {`Saved (${savedCount})`}
      </ToggleGroupItem>
      <ToggleGroupItem value="others" aria-label={`Others (${othersCount})`}>
        {`Others (${othersCount})`}
      </ToggleGroupItem>
    </ToggleGroup>
  );
}
