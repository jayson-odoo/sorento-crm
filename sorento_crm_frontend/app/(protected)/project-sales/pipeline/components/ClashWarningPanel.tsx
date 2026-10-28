'use client';

import Link from 'next/link';
import { AlertTriangle, Info, Loader2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import type { ClashCandidate } from '../../_shared/types/project.types';

/**
 * Shows what the system already knows about this development, once the user checks
 * the title (the Check button beside it) or submits.
 *
 * One line per candidate (PROJECT-REGISTER-V2 D2/D3), in two visually distinct halves:
 *
 * - A BLOCKING match means someone else owns this pursuit. The user cannot register; the
 *   form's one primary becomes "Register interest in <code>", so the line carries no
 *   button of its own.
 * - A CONTEXT match means "this looks similar, is it the same one?". The user registers
 *   normally. Rendering these identically is what trains people to dismiss the warning
 *   without reading it, at which point the blocking case stops working too.
 */
export function ClashWarningPanel({
  candidates,
  isLoading,
}: {
  candidates: ClashCandidate[];
  isLoading?: boolean;
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
    <div className="space-y-2" aria-live="polite">
      {blocking.map((candidate) => (
        <ClashLine
          key={candidate.project_id}
          candidate={candidate}
          label="Project already registered:"
          tone="blocking"
        />
      ))}
      {context.map((candidate) => (
        <ClashLine
          key={candidate.project_id}
          candidate={candidate}
          label="Similar project:"
          tone="context"
        />
      ))}
    </div>
  );
}

function ClashLine({
  candidate,
  label,
  tone,
}: {
  candidate: ClashCandidate;
  label: string;
  tone: 'blocking' | 'context';
}) {
  const Icon = tone === 'blocking' ? AlertTriangle : Info;
  return (
    <div
      className={
        tone === 'blocking'
          ? 'flex items-center gap-2 rounded-lg border border-destructive/40 bg-destructive/5 px-3 py-2'
          : 'flex items-center gap-2 rounded-lg border border-border bg-muted/40 px-3 py-2'
      }
    >
      <Icon
        className={
          tone === 'blocking'
            ? 'size-4 shrink-0 text-destructive'
            : 'size-4 shrink-0 text-muted-foreground'
        }
        aria-hidden
      />
      <p className="flex min-w-0 flex-1 items-baseline gap-1 text-sm">
        <span className="shrink-0">{label}</span>{' '}
        <Link
          href={`/project-sales/${candidate.project_id}`}
          className="shrink-0 font-medium underline-offset-2 hover:underline"
        >
          {candidate.project_code}
        </Link>{' '}
        <span className="min-w-0 truncate" title={candidate.title}>
          {candidate.title}
        </span>
        {candidate.outcome !== 'open' && (
          <Badge variant="secondary" className="shrink-0 capitalize">
            {candidate.outcome}
          </Badge>
        )}
      </p>
    </div>
  );
}
