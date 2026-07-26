import { describe, expect, it } from 'vitest';
import {
  defaultPhaseForProject,
  groupTasksByCategory,
  requiredContextForStatus,
} from './taskGrouping';
import type { Project, ProjectTask } from '../types/project.types';

function project(overrides: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    project_code: 'PRJ-000001',
    title: 'Menara Test',
    outcome: 'open',
    is_critical: false,
    brands: [],
    brand_ids: [],
    next_action_overdue: false,
    open_task_count: 0,
    can_edit: true,
    ...overrides,
  };
}

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

describe('defaultPhaseForProject', () => {
  it('opens on pursuit while the project is still being chased', () => {
    expect(defaultPhaseForProject(project({ outcome: 'open' }))).toBe('pursuit');
  });

  it('opens on delivery once the project is won, because pursuit work is finished', () => {
    expect(defaultPhaseForProject(project({ outcome: 'won' }))).toBe('delivery');
  });

  it('stays on pursuit for a lost or dormant project so the record reads as it was worked', () => {
    expect(defaultPhaseForProject(project({ outcome: 'lost' }))).toBe('pursuit');
    expect(defaultPhaseForProject(project({ outcome: 'dormant' }))).toBe('pursuit');
  });
});

describe('groupTasksByCategory', () => {
  it('groups into sections keyed by category, preserving first-seen order', () => {
    const groups = groupTasksByCategory([
      task({ id: 'a', category: 'Spec-in' }),
      task({ id: 'b', category: 'Commercial' }),
      task({ id: 'c', category: 'Spec-in' }),
    ]);

    expect(groups.map((group) => group.category)).toEqual(['Spec-in', 'Commercial']);
    expect(groups[0].tasks.map((row) => row.id)).toEqual(['a', 'c']);
  });

  it('collects uncategorised tasks into one section that sorts last', () => {
    const groups = groupTasksByCategory([
      task({ id: 'a', category: null }),
      task({ id: 'b', category: 'Spec-in' }),
    ]);

    expect(groups.map((group) => group.category)).toEqual(['Spec-in', null]);
    expect(groups[1].label).toBe('Uncategorised');
  });

  it('counts open and overdue per section, because the section header is the summary', () => {
    const groups = groupTasksByCategory([
      task({ id: 'a', category: 'Spec-in', is_open: true, is_overdue: true }),
      task({ id: 'b', category: 'Spec-in', is_open: true, is_overdue: false }),
      task({ id: 'c', category: 'Spec-in', is_open: false, is_overdue: false }),
    ]);

    expect(groups[0].total).toBe(3);
    expect(groups[0].openCount).toBe(2);
    expect(groups[0].overdueCount).toBe(1);
  });

  it('orders tasks inside a section by sort_order, not by arrival', () => {
    const groups = groupTasksByCategory([
      task({ id: 'late', category: 'Spec-in', sort_order: 20 }),
      task({ id: 'early', category: 'Spec-in', sort_order: 10 }),
    ]);

    expect(groups[0].tasks.map((row) => row.id)).toEqual(['early', 'late']);
  });
});

describe('requiredContextForStatus', () => {
  it('demands an escalation target when moving to escalate', () => {
    expect(requiredContextForStatus('escalate')).toBe('escalated_to_user_id');
  });

  it('demands a reason when moving to stuck', () => {
    expect(requiredContextForStatus('stuck')).toBe('stuck_reason');
  });

  it('demands nothing for an ordinary rung, so the move happens in one click', () => {
    expect(requiredContextForStatus('in_progress')).toBeNull();
    expect(requiredContextForStatus('done')).toBeNull();
    expect(requiredContextForStatus(null)).toBeNull();
  });
});
