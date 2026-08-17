import { describe, expect, it } from 'vitest';
import { bucketTasksByUrgency } from './taskUrgency';
import type { ProjectTask } from '../types/project.types';

function task(overrides: Partial<ProjectTask> = {}): ProjectTask {
  return {
    id: 't1',
    project_id: 'p1',
    name: 'Task',
    task_phase: 'pursuit',
    is_open: true,
    is_overdue: false,
    sort_order: 0,
    can_edit: true,
    ...overrides,
  };
}

describe('bucketTasksByUrgency', () => {
  it('reads overdue from the server flag, never from the browser clock', () => {
    // days_until_due deliberately disagrees: the server is the authority on lateness,
    // because a client in another timezone must not reclassify the row.
    const buckets = bucketTasksByUrgency([
      task({ id: 'a', is_overdue: true, days_until_due: 3, due_date: '2026-07-30' }),
    ]);

    expect(buckets.map((bucket) => bucket.id)).toEqual(['overdue']);
    expect(buckets[0].tasks.map((row) => row.id)).toEqual(['a']);
  });

  it('splits the rest into today, this week and later', () => {
    const buckets = bucketTasksByUrgency([
      task({ id: 'today', days_until_due: 0, due_date: '2026-07-26' }),
      task({ id: 'week', days_until_due: 5, due_date: '2026-07-31' }),
      task({ id: 'later', days_until_due: 40, due_date: '2026-09-04' }),
    ]);

    expect(buckets.map((bucket) => bucket.id)).toEqual(['today', 'week', 'later']);
  });

  it('puts undated work in its own bucket, last', () => {
    const buckets = bucketTasksByUrgency([
      task({ id: 'undated' }),
      task({ id: 'overdue', is_overdue: true, due_date: '2026-07-01' }),
    ]);

    expect(buckets.map((bucket) => bucket.id)).toEqual(['overdue', 'undated']);
    expect(buckets[1].label).toBe('No due date');
  });

  it('drops empty buckets, so an empty heading never implies missing work', () => {
    const buckets = bucketTasksByUrgency([task({ days_until_due: 0, due_date: '2026-07-26' })]);

    expect(buckets).toHaveLength(1);
    expect(buckets[0].id).toBe('today');
  });

  it('returns nothing at all for an empty list', () => {
    expect(bucketTasksByUrgency([])).toEqual([]);
  });
});
