'use client';

import { AlertTriangle, Info, Loader2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { describeLastActivity } from '../../_shared/lib/lastActivity';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { ClashCandidate } from '../../_shared/types/project.types';

/**
 * Shows what the system already knows about this development, while the user is
 * still typing the title.
 *
 * Two visually distinct halves, because the two cases need different actions:
 *
 * - A BLOCKING match means someone else owns this pursuit, OR the developer is still
 *   unstated and so sameness cannot be ruled out. The user cannot save; the way forward
 *   is to name a different developer, ask to join, or dispute it.
 * - A CONTEXT match means "this looks similar, is it the same one?". The user saves
 *   normally. Rendering these identically is what trains people to dismiss the
 *   warning without reading it, at which point the blocking case stops working too.
 */
export function ClashWarningPanel({
  candidates,
  isLoading,
  developerChosen = true,
  onRequestJoin,
  onDispute,
}: {
  candidates: ClashCandidate[];
  isLoading?: boolean;
  /** False while the Developer field is empty, which is a blocking reason of its own. */
  developerChosen?: boolean;
  onRequestJoin?: (candidate: ClashCandidate) => void;
  onDispute?: (candidate: ClashCandidate) => void;
}) {
  if (isLoading && candidates.length === 0) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/40 px-3 py-2.5 text-sm text-muted-foreground">
        <Loader2 className="size-3.5 shrink-0 animate-spin" aria-hidden />
        <span>Checking for existing projects…</span>
      </div>
    );
  }

  if (candidates.length === 0) return null;

  const blocking = candidates.filter((candidate) => candidate.blocks);
  const context = candidates.filter((candidate) => !candidate.blocks);

  return (
    <div className="space-y-3" aria-live="polite">
      {blocking.length > 0 && (
        <section className="rounded-lg border border-destructive/40 bg-destructive/5 p-3">
          <header className="flex items-start gap-2">
            <AlertTriangle
              className="mt-0.5 size-4 shrink-0 text-destructive"
              aria-hidden
            />
            <div className="min-w-0">
              <h4 className="text-sm font-semibold text-destructive">
                Already registered to someone else
              </h4>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {developerChosen
                  ? 'One development, one owner. Ask to join it, or raise a dispute for a manager to decide.'
                  : 'One development, one owner. Name the developer below if yours is a different one, or ask to join it.'}
              </p>
            </div>
          </header>
          <ul className="mt-3 space-y-2">
            {blocking.map((candidate) => (
              <IncumbentRow
                key={candidate.project_id}
                candidate={candidate}
                tone="blocking"
                onRequestJoin={onRequestJoin}
                onDispute={onDispute}
              />
            ))}
          </ul>
        </section>
      )}

      {context.length > 0 && (
        <section className="rounded-lg border border-border bg-muted/40 p-3">
          <header className="flex items-start gap-2">
            <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
            <div className="min-w-0">
              <h4 className="text-sm font-semibold text-foreground">
                Similar projects
              </h4>
            </div>
          </header>
          <ul className="mt-3 space-y-2">
            {context.map((candidate) => (
              <IncumbentRow key={candidate.project_id} candidate={candidate} tone="context" />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function IncumbentRow({
  candidate,
  tone,
  onRequestJoin,
  onDispute,
}: {
  candidate: ClashCandidate;
  tone: 'blocking' | 'context';
  onRequestJoin?: (candidate: ClashCandidate) => void;
  onDispute?: (candidate: ClashCandidate) => void;
}) {
  return (
    <li
      className={cn(
        'rounded-md border bg-background p-2.5',
        tone === 'blocking' ? 'border-destructive/30' : 'border-border',
      )}
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-sm text-muted-foreground">
              {candidate.project_code}
            </span>
            <span className="truncate text-sm font-medium" title={candidate.title}>
              {candidate.title}
            </span>
            {candidate.outcome !== 'open' && (
              <Badge variant="secondary" className="capitalize">
                {candidate.outcome}
              </Badge>
            )}
          </div>
          <dl className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-muted-foreground">
            <Fact label="Owner" value={candidate.owner_name ?? 'Unassigned'} />
            <Fact label="Developer" value={candidate.developer_name} />
            <Fact label="Stage" value={candidate.status_label} />
            <Fact
              label="Estimated"
              value={
                candidate.estimated_sales_value
                  ? formatMyr(candidate.estimated_sales_value)
                  : null
              }
            />
            <Fact label="Last activity" value={describeLastActivity(candidate.last_activity_at)} />
          </dl>
          {candidate.brands.length > 0 && (
            <div className="flex flex-wrap gap-1 pt-0.5">
              {candidate.brands.map((brand) => (
                <Badge key={brand} variant="outline" className="text-[11px]">
                  {brand}
                </Badge>
              ))}
            </div>
          )}
        </div>

        {tone === 'blocking' && (onRequestJoin || onDispute) && (
          <div className="flex shrink-0 flex-wrap gap-2">
            {onRequestJoin && (
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => onRequestJoin(candidate)}
              >
                Ask to join
              </Button>
            )}
            {onDispute && (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => onDispute(candidate)}
              >
                Dispute
              </Button>
            )}
          </div>
        )}
      </div>
    </li>
  );
}

function Fact({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null;
  return (
    <div className="flex gap-1">
      <dt className="text-muted-foreground/70">{label}:</dt>
      <dd className="text-foreground">{value}</dd>
    </div>
  );
}

function formatMyr(value: string): string {
  const amount = Number(value);
  if (Number.isNaN(amount)) return value;
  return `RM ${amount.toLocaleString('en-MY', { maximumFractionDigits: 0 })}`;
}

