'use client';

import * as React from 'react';
import Link from 'next/link';
import { AlertTriangle, CalendarClock, Clock, Flame, GripVertical } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { STALE_TONE_CLASS, describeStaleness } from '../../_shared/lib/staleness';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import type { Status } from '@/app/(protected)/system-management/status-graphs/types/statusGraph.types';
import type { Project } from '../../_shared/types/project.types';

/**
 * The pipeline as columns of configured statuses (AC-G3).
 *
 * Drag is HTML5 drag-and-drop rather than a library: a card carries only its id, the
 * drop asks the server for the transition, and the list is refetched either way. That
 * is what makes an illegal move snap back (the server rejects it and the refetch puts
 * the card where it really is) instead of leaving the board lying about the data.
 */
export function PipelineBoard({
  statuses,
  projects,
  isLoading,
  onMove,
  movingProjectId,
}: {
  statuses: Status[];
  projects: Project[];
  isLoading?: boolean;
  onMove: (projectId: string, toStatusId: string) => void;
  movingProjectId?: string | null;
}) {
  const [dragProjectId, setDragProjectId] = React.useState<string | null>(null);
  const [hoverStatusId, setHoverStatusId] = React.useState<string | null>(null);

  const columns = React.useMemo(() => {
    const grouped = new Map<string, Project[]>();
    statuses.forEach((status) => grouped.set(status.id, []));
    const unplaced: Project[] = [];
    projects.forEach((project) => {
      if (project.status_id && grouped.has(project.status_id)) {
        grouped.get(project.status_id)!.push(project);
      } else {
        unplaced.push(project);
      }
    });
    return { grouped, unplaced };
  }, [statuses, projects]);

  if (isLoading) {
    return (
      <div className="flex gap-4 overflow-x-auto pb-2">
        {[0, 1, 2, 3].map((index) => (
          <div key={index} className="w-72 shrink-0 space-y-3">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        ))}
      </div>
    );
  }

  if (statuses.length === 0) {
    return (
      <EmptyState
        title="No pipeline stages configured"
        body="The board shows one column per configured project status. Set them up under System Management → Status Graphs, then projects will appear here."
        actionHref="/system-management/status-graphs"
        actionLabel="Configure stages"
      />
    );
  }

  return (
    <div className="space-y-4">
      {columns.unplaced.length > 0 && (
        <section className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-3">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <AlertTriangle className="size-4 text-amber-600" aria-hidden />
            {columns.unplaced.length} project
            {columns.unplaced.length === 1 ? '' : 's'} with no stage
          </h3>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Registered before the pipeline was configured, or imported. Open each one and
            move it to its stage.
          </p>
          <ul className="mt-2 flex flex-wrap gap-2">
            {columns.unplaced.map((project) => (
              <li key={project.id}>
                <Link
                  href={`/project-sales/${project.id}`}
                  className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-2 py-1 text-xs hover:bg-accent"
                >
                  <span className="text-muted-foreground">
                    {project.project_code}
                  </span>
                  <span className="max-w-[16rem] truncate" title={project.title}>
                    {project.title}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="flex gap-4 overflow-x-auto pb-3">
        {statuses.map((status) => {
          const cards = columns.grouped.get(status.id) ?? [];
          const isTarget = hoverStatusId === status.id && dragProjectId !== null;
          return (
            <section
              key={status.id}
              className={cn(
                'flex w-72 shrink-0 flex-col rounded-lg border bg-muted/30 transition-colors',
                isTarget ? 'border-primary bg-primary/5' : 'border-border',
              )}
              onDragOver={(event) => {
                event.preventDefault();
                setHoverStatusId(status.id);
              }}
              onDragLeave={() => setHoverStatusId((current) => (current === status.id ? null : current))}
              onDrop={(event) => {
                event.preventDefault();
                setHoverStatusId(null);
                const projectId = event.dataTransfer.getData('text/plain') || dragProjectId;
                setDragProjectId(null);
                if (projectId) onMove(projectId, status.id);
              }}
            >
              <header className="flex items-center justify-between gap-2 border-b border-border px-3 py-2">
                <h3 className="truncate text-sm font-semibold" title={status.label}>
                  {status.label}
                </h3>
                <Badge variant="secondary" className="shrink-0">
                  {cards.length}
                </Badge>
              </header>

              <ul className="flex min-h-24 flex-col gap-2 p-2">
                {cards.length === 0 ? (
                  <li className="rounded-md border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">
                    {status.is_terminal ? 'Nothing closed here yet' : 'Drop a project here'}
                  </li>
                ) : (
                  cards.map((project) => (
                    <ProjectCard
                      key={project.id}
                      project={project}
                      isMoving={movingProjectId === project.id}
                      onDragStart={(event) => {
                        event.dataTransfer.setData('text/plain', project.id);
                        event.dataTransfer.effectAllowed = 'move';
                        setDragProjectId(project.id);
                      }}
                      onDragEnd={() => {
                        setDragProjectId(null);
                        setHoverStatusId(null);
                      }}
                    />
                  ))
                )}
              </ul>
            </section>
          );
        })}
      </div>
    </div>
  );
}

function ProjectCard({
  project,
  isMoving,
  onDragStart,
  onDragEnd,
}: {
  project: Project;
  isMoving?: boolean;
  onDragStart: (event: React.DragEvent) => void;
  onDragEnd: () => void;
}) {
  // Only a project the user may edit is draggable. A card that moves and then snaps
  // back with a 403 is worse than one that never moved.
  const draggable = project.can_edit;
  // The server stamps the rung per status threshold (AC-H4/H6). This card used to guess
  // with a flat 30 days, which was wrong in both directions: 30 days is fine at Registered
  // and far too long at Tendering.
  const stale = describeStaleness(project);
  const nextAction = describeNextAction(project);

  return (
    <li
      draggable={draggable}
      onDragStart={draggable ? onDragStart : undefined}
      onDragEnd={draggable ? onDragEnd : undefined}
      className={cn(
        'rounded-md border border-border bg-background p-2.5 shadow-xs transition-opacity',
        draggable ? 'cursor-grab active:cursor-grabbing' : 'cursor-default',
        isMoving && 'opacity-50',
      )}
    >
      <div className="flex items-start gap-1.5">
        {draggable && (
          <GripVertical
            className="mt-0.5 size-3.5 shrink-0 text-muted-foreground/60"
            aria-hidden
          />
        )}
        <div className="min-w-0 flex-1 space-y-1.5">
          <Link
            href={`/project-sales/${project.id}`}
            className="block space-y-0.5 hover:underline"
          >
            <span className="text-xs text-muted-foreground">
              {project.project_code}
            </span>
            <p className="line-clamp-2 text-sm font-medium leading-snug" title={project.title}>
              {project.title}
            </p>
          </Link>

          {project.developer_name && (
            <p className="truncate text-xs text-muted-foreground" title={project.developer_name}>
              {project.developer_name}
            </p>
          )}

          <div className="flex flex-wrap items-center gap-1">
            {project.is_critical && (
              <Badge variant="destructive" className="gap-1 text-[11px]">
                <Flame className="size-3" aria-hidden />
                Critical
              </Badge>
            )}
            {stale && (
              <Badge
                variant="outline"
                className={`gap-1 text-[11px] ${STALE_TONE_CLASS[stale.tone as 'notice']}`}
                title={stale.detail}
              >
                <Clock className="size-3" aria-hidden />
                {stale.label}
              </Badge>
            )}
            {project.brands.slice(0, 2).map((brand) => (
              <Badge key={brand} variant="outline" className="text-[11px]">
                {brand}
              </Badge>
            ))}
            {project.brands.length > 2 && (
              <Badge variant="outline" className="text-[11px]">
                +{project.brands.length - 2}
              </Badge>
            )}
          </div>

          {nextAction && (
            <p
              className={cn(
                'flex items-center gap-1 text-xs',
                project.next_action_overdue ? 'font-medium text-destructive' : 'text-muted-foreground',
              )}
              title={nextAction.title}
            >
              <CalendarClock className="size-3 shrink-0" aria-hidden />
              <span className="truncate">{nextAction.label}</span>
            </p>
          )}

          <div className="flex items-center justify-between gap-2 pt-0.5 text-xs">
            <span className="truncate text-muted-foreground" title={project.owner_name ?? ''}>
              {project.owner_name ?? 'Unassigned'}
            </span>
            {project.estimated_sales_value && (
              <span className="shrink-0 font-medium">
                {formatMyrShort(project.estimated_sales_value)}
              </span>
            )}
          </div>
        </div>
      </div>
    </li>
  );
}

/**
 * The card's next-action line (AC-N6).
 *
 * Server-derived from the earliest open task, so this only formats it. Three distinct
 * states, and none of them may render as blank: a dated action, open work that nobody
 * has dated, and genuinely nothing open. The middle one is the reason a bare date field
 * is not enough -- "no date" is not the same as "nothing to do".
 */
function describeNextAction(project: Project): { label: string; title: string } | null {
  if (project.next_action_date) {
    return {
      label: formatNextActionDate(project.next_action_date),
      title: project.next_action_overdue
        ? `Next action ${formatNextActionDate(project.next_action_date)}, overdue`
        : `Next action ${formatNextActionDate(project.next_action_date)}`,
    };
  }
  if (project.open_task_count > 0) {
    return {
      label: `${project.open_task_count} open, none dated`,
      title: `Next action: ${project.open_task_count} open task${project.open_task_count === 1 ? '' : 's'}, none with a due date`,
    };
  }
  return null;
}

function formatNextActionDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString('en-MY', { day: '2-digit', month: 'short', year: 'numeric' });
}

export function EmptyState({
  title,
  body,
  actionHref,
  actionLabel,
}: {
  title: string;
  body: string;
  actionHref?: string;
  actionLabel?: string;
}) {
  return (
    <div className="rounded-lg border border-dashed border-border px-6 py-12 text-center">
      <h3 className="text-sm font-semibold">{title}</h3>
      <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">{body}</p>
      {actionHref && actionLabel && (
        <Link
          href={actionHref}
          className="mt-4 inline-flex items-center rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          {actionLabel}
        </Link>
      )}
    </div>
  );
}

function formatMyrShort(value: string): string {
  const amount = Number(value);
  if (Number.isNaN(amount)) return value;
  if (amount >= 1_000_000) return `RM ${(amount / 1_000_000).toFixed(1)}m`;
  if (amount >= 1_000) return `RM ${Math.round(amount / 1_000)}k`;
  return `RM ${amount.toFixed(0)}`;
}
