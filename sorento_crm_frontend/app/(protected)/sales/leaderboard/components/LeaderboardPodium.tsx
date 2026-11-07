'use client';

import { cn } from '@/lib/utils';
import type { LeaderboardRow } from '@/services/salesLeaderboardService';
import { changeTone, codesText, formatChange, formatCompactRm, formatRm } from './leaderboardFormat';

const MEDAL: Record<number, string> = {
  1: 'bg-amber-500',
  2: 'bg-slate-400',
  3: 'bg-orange-700',
};

/** #1 in the middle: 2, 1, 3. Fewer than three rows show only those, in rank order. */
function podiumOrder(rows: LeaderboardRow[]): LeaderboardRow[] {
  const top = rows.slice(0, 3);
  if (top.length < 3) return top;
  return [top[1], top[0], top[2]];
}

export function LeaderboardPodium({
  rows,
  versus,
  showChange = true,
  canOpen,
  onOpen,
}: {
  rows: LeaderboardRow[];
  /** `Sep`, `previous period` */
  versus: string;
  /** False on Undelivered, which has no earlier window. */
  showChange?: boolean;
  /** A card opens its row exactly when the row would open (same handler as the grid). */
  canOpen?: (row: LeaderboardRow) => boolean;
  onOpen?: (row: LeaderboardRow) => void;
}) {
  const cards = podiumOrder(rows);
  if (cards.length === 0) return null;
  return (
    <div
      data-testid="leaderboard-podium"
      className="grid items-end gap-1.5 md:gap-3"
      style={{ gridTemplateColumns: cards.length === 3 ? '1fr 1.15fr 1fr' : `repeat(${cards.length}, 1fr)` }}
    >
      {cards.map((row) => {
        const person = row.person ?? row.name;
        const codes = row.codes ?? [];
        const open = onOpen && canOpen?.(row);
        const Card = open ? 'button' : 'div';
        return (
        <Card
          key={row.rank}
          data-testid={`leaderboard-podium-${row.rank}`}
          data-drill={open ? 'true' : undefined}
          {...(open ? { type: 'button' as const, onClick: () => onOpen(row) } : {})}
          className={cn(
            open && 'cursor-pointer hover:bg-muted/40',
            'min-w-0 rounded-lg border border-border p-2 text-center md:p-4',
            row.rank === 1 && 'border-amber-500 ring-1 ring-amber-500 md:pt-6',
            row.is_me && 'bg-primary/5',
          )}
        >
          <span
            className={cn(
              'mb-1.5 inline-flex size-6 items-center justify-center rounded-full text-xs font-bold text-white md:size-7 md:text-sm',
              MEDAL[row.rank],
            )}
          >
            {row.rank}
          </span>
          <span className="block truncate text-xs font-semibold md:text-sm" title={person}>
            {person}
          </span>
          {codesText(person, codes) ? (
            <span
              className="hidden truncate text-xs text-muted-foreground md:block"
              title={codesText(person, codes)}
            >
              {codesText(person, codes)}
            </span>
          ) : null}
          <span className="block mt-1 text-sm font-bold tabular-nums md:text-xl">
            <span className="md:hidden">{formatCompactRm(row.amount)}</span>
            <span className="hidden md:inline">{formatRm(row.amount)}</span>
          </span>
          {showChange ? (
            <span className={cn('hidden text-xs md:block', changeTone(row.change_pct))}>
              {row.change_pct === null ? '-' : `${formatChange(row.change_pct)} vs ${versus}`}
            </span>
          ) : null}
        </Card>
        );
      })}
    </div>
  );
}
