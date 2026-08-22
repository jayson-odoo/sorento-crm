import { describe, expect, it } from 'vitest';
import { buildTaskTimeline } from './taskTimeline';
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

describe('buildTaskTimeline', () => {
  it('returns nothing to draw when no task carries a date', () => {
    const timeline = buildTaskTimeline([task({ id: 'a' }), task({ id: 'b' })]);

    expect(timeline.bars).toEqual([]);
    expect(timeline.undated.map((row) => row.id)).toEqual(['a', 'b']);
    expect(timeline.months).toEqual([]);
  });

  it('spans from the earliest date to the latest, whichever field they came from', () => {
    const timeline = buildTaskTimeline([
      task({ id: 'a', start_date: '2026-03-10', due_date: '2026-03-20' }),
      task({ id: 'b', due_date: '2026-05-05' }),
    ]);

    expect(timeline.start).toBe('2026-03-10');
    expect(timeline.end).toBe('2026-05-05');
  });

  it('places a bar proportionally inside the span', () => {
    // Span 2026-01-01 to 2026-01-11 is 10 days. A bar on day 5 to day 6 starts at 40%.
    const timeline = buildTaskTimeline([
      task({ id: 'edges', start_date: '2026-01-01', due_date: '2026-01-11' }),
      task({ id: 'mid', start_date: '2026-01-05', due_date: '2026-01-06' }),
    ]);

    const mid = timeline.bars.find((bar) => bar.task.id === 'mid');
    expect(mid?.leftPercent).toBeCloseTo(40, 5);
    expect(mid?.widthPercent).toBeCloseTo(10, 5);
  });

  it('gives a start-less task a bar on its due date alone, so it is still visible', () => {
    const timeline = buildTaskTimeline([
      task({ id: 'span', start_date: '2026-01-01', due_date: '2026-01-11' }),
      task({ id: 'due-only', due_date: '2026-01-06' }),
    ]);

    const bar = timeline.bars.find((row) => row.task.id === 'due-only');
    expect(bar?.leftPercent).toBeCloseTo(50, 5);
    // A zero-width bar would be invisible, so it gets a minimum.
    expect(bar?.widthPercent).toBeGreaterThan(0);
  });

  it('never returns a zero-width span, so a single-date timeline still renders', () => {
    const timeline = buildTaskTimeline([task({ id: 'only', due_date: '2026-01-06' })]);

    expect(timeline.bars).toHaveLength(1);
    expect(timeline.bars[0].widthPercent).toBeGreaterThan(0);
    expect(timeline.bars[0].leftPercent).toBeGreaterThanOrEqual(0);
    expect(timeline.bars[0].leftPercent + timeline.bars[0].widthPercent).toBeLessThanOrEqual(100);
  });

  it('labels one gridline per month the span touches', () => {
    const timeline = buildTaskTimeline([
      task({ id: 'a', start_date: '2026-01-20', due_date: '2026-03-05' }),
    ]);

    expect(timeline.months.map((month) => month.label)).toEqual(['Jan 2026', 'Feb 2026', 'Mar 2026']);
    expect(timeline.months[0].leftPercent).toBe(0);
  });

  it('keeps undated tasks out of the bars but still reports them', () => {
    const timeline = buildTaskTimeline([
      task({ id: 'dated', due_date: '2026-01-06' }),
      task({ id: 'undated' }),
    ]);

    expect(timeline.bars.map((bar) => bar.task.id)).toEqual(['dated']);
    expect(timeline.undated.map((row) => row.id)).toEqual(['undated']);
  });
});
