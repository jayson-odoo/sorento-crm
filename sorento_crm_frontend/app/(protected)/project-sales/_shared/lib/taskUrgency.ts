import type { ProjectTask } from '../types/project.types';

/**
 * Urgency buckets for the cross-project worklist.
 *
 * Lateness comes from the server's `is_overdue` and `days_until_due`, never from
 * `new Date()` here. The server computes both in Malaysia time; a browser in another
 * timezone re-deriving them would silently move rows between buckets around midnight.
 */

export type UrgencyBucketId = 'overdue' | 'today' | 'week' | 'later' | 'undated';

export interface UrgencyBucket {
  id: UrgencyBucketId;
  label: string;
  tasks: ProjectTask[];
}

const ORDER: { id: UrgencyBucketId; label: string }[] = [
  { id: 'overdue', label: 'Overdue' },
  { id: 'today', label: 'Due today' },
  { id: 'week', label: 'Due this week' },
  { id: 'later', label: 'Later' },
  { id: 'undated', label: 'No due date' },
];

function bucketFor(task: ProjectTask): UrgencyBucketId {
  if (task.is_overdue) return 'overdue';
  if (!task.due_date) return 'undated';
  const days = task.days_until_due;
  if (days === null || days === undefined) return 'later';
  if (days <= 0) return 'today';
  if (days <= 7) return 'week';
  return 'later';
}

/**
 * Empty buckets are dropped rather than rendered with a zero: a heading with nothing
 * under it reads as work that failed to load.
 */
export function bucketTasksByUrgency(tasks: ProjectTask[]): UrgencyBucket[] {
  const grouped = new Map<UrgencyBucketId, ProjectTask[]>();
  for (const task of tasks) {
    const id = bucketFor(task);
    const existing = grouped.get(id);
    if (existing) existing.push(task);
    else grouped.set(id, [task]);
  }

  return ORDER.filter((bucket) => (grouped.get(bucket.id) ?? []).length > 0).map((bucket) => ({
    ...bucket,
    tasks: grouped.get(bucket.id) as ProjectTask[],
  }));
}
