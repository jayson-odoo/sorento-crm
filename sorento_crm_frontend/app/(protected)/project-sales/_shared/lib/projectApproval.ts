import type { Project, ProjectApprovalState } from '../types/project.types';

/** A staff-registered project (no approval state) or an approved portal registration. */
export function isProjectApproved(project: { approval_state?: ProjectApprovalState | null }): boolean {
  return project.approval_state == null || project.approval_state === 'approved';
}

/**
 * May this user add work to the project (tasks, stakeholders, quotations, samples, POs,
 * schedules, sales orders)? The edit right AND an approved project: the server answers 409
 * `project_not_approved` for a registration that is still waiting (PROJECT-REG-PORTAL R4),
 * so its tabs offer no button that would only be refused.
 */
export function canWorkOnProject(project: Pick<Project, 'can_edit' | 'approval_state'>): boolean {
  return Boolean(project.can_edit) && isProjectApproved(project);
}
