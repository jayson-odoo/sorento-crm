/**
 * A project read page opens for `.view` (every project) or `.view_own` (the salesperson's own).
 * `projects.import.view` is here so a user holding only it gets past the Project Sales layout
 * gate to the Project import screen (PLAN-project-import-12nov.md, "Frontend contract").
 */
export const PROJECT_VIEW_PERMISSIONS = [
  'projects.projects.view',
  'projects.projects.view_own',
  'projects.import.view',
];
