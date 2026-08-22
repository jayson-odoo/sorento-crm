import type { ProjectTask } from '../types/project.types';

/**
 * Geometry for the Tasks tab timeline view (AC-N7 / AC-N7a).
 *
 * A timeline bar chart of start and due dates. There are deliberately NO dependency
 * arrows and no critical path: a project task has no predecessor field, so drawing
 * links would be inventing information the data does not carry.
 *
 * All arithmetic is on plain `YYYY-MM-DD` strings parsed as UTC midnight, so a browser
 * in any timezone puts a bar in the same place. Percentages are returned rather than
 * pixels so the chart reflows with the container.
 */

const DAY_MS = 86_400_000;
/** A one-day task on a one-year span would round to 0.27% and vanish. */
const MIN_WIDTH_PERCENT = 1.5;

export interface TaskTimelineBar {
  task: ProjectTask;
  leftPercent: number;
  widthPercent: number;
}

export interface TaskTimelineMonth {
  label: string;
  leftPercent: number;
}

export interface TaskTimeline {
  /** Null when nothing is dated. */
  start: string | null;
  end: string | null;
  bars: TaskTimelineBar[];
  months: TaskTimelineMonth[];
  /** Real work with no dates. Listed separately rather than dropped. */
  undated: ProjectTask[];
}

function toUtcDay(iso?: string | null): number | null {
  if (!iso) return null;
  const value = Date.parse(`${iso.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(value) ? null : value;
}

function toIsoDay(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10);
}

export function buildTaskTimeline(tasks: ProjectTask[]): TaskTimeline {
  const dated: { task: ProjectTask; from: number; to: number }[] = [];
  const undated: ProjectTask[] = [];

  for (const task of tasks) {
    const start = toUtcDay(task.start_date);
    const due = toUtcDay(task.due_date);
    if (start === null && due === null) {
      undated.push(task);
      continue;
    }
    const from = start ?? (due as number);
    const to = due ?? (start as number);
    dated.push({ task, from: Math.min(from, to), to: Math.max(from, to) });
  }

  if (dated.length === 0) {
    return { start: null, end: null, bars: [], months: [], undated };
  }

  const spanStart = Math.min(...dated.map((entry) => entry.from));
  const spanEnd = Math.max(...dated.map((entry) => entry.to));
  // A span of one single day would divide by zero; give it a day of width.
  const spanMs = Math.max(spanEnd - spanStart, DAY_MS);

  const bars = dated.map((entry) => {
    const rawLeft = ((entry.from - spanStart) / spanMs) * 100;
    const rawWidth = ((entry.to - entry.from) / spanMs) * 100;
    const widthPercent = Math.max(rawWidth, MIN_WIDTH_PERCENT);
    // Clamp so a widened bar at the far right does not overflow the track.
    const leftPercent = Math.min(Math.max(rawLeft, 0), 100 - widthPercent);
    return { task: entry.task, leftPercent, widthPercent };
  });

  const months: TaskTimelineMonth[] = [];
  const cursor = new Date(spanStart);
  cursor.setUTCDate(1);
  while (cursor.getTime() <= spanEnd) {
    const offset = ((cursor.getTime() - spanStart) / spanMs) * 100;
    months.push({
      label: `${cursor.toLocaleString('en-MY', { month: 'short', timeZone: 'UTC' })} ${cursor.getUTCFullYear()}`,
      leftPercent: Math.max(offset, 0),
    });
    cursor.setUTCMonth(cursor.getUTCMonth() + 1);
  }

  return {
    start: toIsoDay(spanStart),
    end: toIsoDay(spanEnd),
    bars,
    months,
    undated,
  };
}
