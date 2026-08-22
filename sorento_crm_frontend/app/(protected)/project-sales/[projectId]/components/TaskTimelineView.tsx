'use client';

import * as React from 'react';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { buildTaskTimeline } from '../../_shared/lib/taskTimeline';
import type { ProjectTask } from '../../_shared/types/project.types';

/**
 * The tasks as bars over a date axis (AC-N7, AC-N7a).
 *
 * A timeline, NOT a dependency chart: a project task has no predecessor field, so there
 * are no arrows and no critical path. Saying so here stops the next reader assuming the
 * feature was forgotten.
 *
 * Undated tasks are listed under the chart rather than dropped. Work with no date is
 * still work, and a chart that silently omits it reads as a shorter project.
 */
export function TaskTimelineView({ tasks }: { tasks: ProjectTask[] }) {
  const timeline = React.useMemo(() => buildTaskTimeline(tasks), [tasks]);

  return (
    <div className="space-y-3">
      {timeline.bars.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border px-6 py-8 text-center">
          <h3 className="text-sm font-semibold">Nothing to plot yet</h3>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            A task needs a start or a due date to appear on the timeline. Give the
            earliest one a date and it becomes this project&apos;s next action too.
          </p>
        </div>
      ) : (
        // Horizontal scroll on the chart only: a long project must never make the whole
        // page scroll sideways.
        <div className="overflow-x-auto">
          <div className="min-w-[36rem] space-y-1">
            <div className="relative ml-[40%] h-5 border-b border-border sm:ml-[30%]">
              {timeline.months.map((month) => (
                <span
                  key={month.label}
                  className="absolute top-0 -translate-x-1/2 whitespace-nowrap text-[11px] text-muted-foreground"
                  style={{ left: `${month.leftPercent}%` }}
                >
                  {month.label}
                </span>
              ))}
            </div>

            <ul className="space-y-1">
              {timeline.bars.map((bar) => (
                <li key={bar.task.id} className="flex items-center gap-2">
                  <span
                    className="w-[40%] shrink-0 truncate text-xs sm:w-[30%]"
                    title={bar.task.name}
                  >
                    {bar.task.name}
                  </span>
                  <span className="relative h-5 flex-1 rounded bg-muted/60">
                    {timeline.months.map((month) => (
                      <span
                        key={month.label}
                        aria-hidden
                        className="absolute inset-y-0 w-px bg-border"
                        style={{ left: `${month.leftPercent}%` }}
                      />
                    ))}
                    <span
                      className={cn(
                        'absolute inset-y-0.5 rounded',
                        bar.task.is_overdue
                          ? 'bg-destructive'
                          : bar.task.is_open
                            ? 'bg-primary'
                            : 'bg-muted-foreground/50',
                      )}
                      style={{
                        left: `${bar.leftPercent}%`,
                        width: `${bar.widthPercent}%`,
                      }}
                      title={describeBar(bar.task)}
                    />
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {timeline.undated.length > 0 && (
        <div className="rounded-lg border border-border p-3">
          <p className="text-xs font-medium">
            {timeline.undated.length} task{timeline.undated.length === 1 ? '' : 's'} with no
            dates
          </p>
          <ul className="mt-1.5 flex flex-wrap gap-1.5">
            {timeline.undated.map((task) => (
              <li key={task.id}>
                <Badge variant="outline" className="max-w-full text-[11px]">
                  <span className="truncate" title={task.name}>
                    {task.name}
                  </span>
                </Badge>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function describeBar(task: ProjectTask): string {
  const window =
    task.start_date && task.due_date
      ? `${task.start_date} to ${task.due_date}`
      : `due ${task.due_date ?? task.start_date}`;
  const status = task.status_label ? `, ${task.status_label}` : '';
  return `${task.name}: ${window}${status}${task.is_overdue ? ', overdue' : ''}`;
}
