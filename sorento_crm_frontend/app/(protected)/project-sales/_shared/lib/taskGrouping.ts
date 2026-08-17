import type { Project, ProjectTask, TaskPhase } from '../types/project.types';

/**
 * Pure view logic for the Tasks tab. Kept out of the component so the two rules that
 * are easy to get subtly wrong can be pinned by tests instead of by clicking.
 */

export interface TaskCategoryGroup {
  /** Null is the real "no category" group, not a missing value. */
  category: string | null;
  label: string;
  tasks: ProjectTask[];
  total: number;
  openCount: number;
  overdueCount: number;
}

export const UNCATEGORISED_LABEL = 'Uncategorised';

/**
 * Which phase the tab opens on.
 *
 * A won project's pursuit checklist is history, so landing there wastes the click.
 * Lost and dormant stay on pursuit: that is the work that was actually done, and
 * there is no delivery to show.
 */
export function defaultPhaseForProject(project: Pick<Project, 'outcome'>): TaskPhase {
  return project.outcome === 'won' ? 'delivery' : 'pursuit';
}

/**
 * Group by work-stream, first-seen order, uncategorised last.
 *
 * First-seen order rather than alphabetical: the caller hands tasks over already
 * ordered by the template's sort_order, so the sections come out in the sequence the
 * template author intended rather than in an arbitrary alphabet.
 */
export function groupTasksByCategory(tasks: ProjectTask[]): TaskCategoryGroup[] {
  const named = new Map<string, TaskCategoryGroup>();
  let uncategorised: TaskCategoryGroup | null = null;

  const blank = (category: string | null): TaskCategoryGroup => ({
    category,
    label: category ?? UNCATEGORISED_LABEL,
    tasks: [],
    total: 0,
    openCount: 0,
    overdueCount: 0,
  });

  for (const task of tasks) {
    let group: TaskCategoryGroup;
    if (task.category) {
      group = named.get(task.category) ?? blank(task.category);
      named.set(task.category, group);
    } else {
      // A separate binding rather than a magic map key: any sentinel string is a
      // category name somebody could legitimately type.
      uncategorised = uncategorised ?? blank(null);
      group = uncategorised;
    }
    group.tasks.push(task);
    group.total += 1;
    if (task.is_open) group.openCount += 1;
    if (task.is_overdue) group.overdueCount += 1;
  }

  const ordered = [...named.values()];
  if (uncategorised) ordered.push(uncategorised);
  for (const group of ordered) {
    group.tasks.sort((a, b) => a.sort_order - b.sort_order);
  }
  return ordered;
}

/**
 * Extra context the server refuses the move without.
 *
 * Branching on the status KEY, never the label: an admin renaming "Stuck" to "Blocked"
 * must not silently turn the reason field optional.
 */
export function requiredContextForStatus(
  statusKey?: string | null,
): 'escalated_to_user_id' | 'stuck_reason' | null {
  if (statusKey === 'escalate') return 'escalated_to_user_id';
  if (statusKey === 'stuck') return 'stuck_reason';
  return null;
}
