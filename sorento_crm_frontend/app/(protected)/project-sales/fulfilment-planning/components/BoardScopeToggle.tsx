'use client';

import { Button } from '@/components/ui/button';

/** `all` is only reached from a link (`?scope=all`): no segment pressed, every line shown. */
export type BoardScope = 'saved' | 'others' | 'all';

/**
 * Saved | Others, the quick check of what Confirm will send against everything else. Built the
 * same way as the board's own Grid | List switch (`FulfilmentBoardPanel`, the "Board view"
 * group): two `Button size="sm"` in a bordered inline group, the pressed one `variant="primary"`
 * (the system's filled blue), the other `ghost`. No custom colour classes.
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
    <div
      className="inline-flex rounded-md border border-input"
      role="group"
      aria-label="Saved or others"
      data-testid="board-scope-toggle"
    >
      <Button
        type="button"
        size="sm"
        variant={value === 'saved' ? 'primary' : 'ghost'}
        className="rounded-e-none"
        aria-pressed={value === 'saved'}
        onClick={() => onChange('saved')}
      >
        {`Saved (${savedCount})`}
      </Button>
      <Button
        type="button"
        size="sm"
        variant={value === 'others' ? 'primary' : 'ghost'}
        className="rounded-s-none border-s border-input"
        aria-pressed={value === 'others'}
        onClick={() => onChange('others')}
      >
        {`Others (${othersCount})`}
      </Button>
    </div>
  );
}
