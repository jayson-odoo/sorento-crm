import type { MenuConfig, MenuItem } from './types';

/** Must match backend `GET .../definitions/published-for-submission` (require_any_permission). */
export const WORKFLOW_PUBLISHED_FOR_SUBMISSION_PERMISSIONS = [
  'workflow_forms.submissions.add',
  'workflow_forms.submissions.view',
  'workflow_forms.definitions.view',
] as const;

/**
 * Append one link per published workflow form (name = form title).
 * Each link goes to the submissions list for that form (with New submission on that page).
 * Must run before permission filtering so submitters without definitions.view still see their forms.
 */
export function injectPublishedWorkflowForms(
  menu: MenuConfig,
  forms: { id: string; name: string }[],
): MenuConfig {
  return menu.map((item) => {
    if (item.title === 'Workflow Forms' && item.moduleKey === 'workflow_forms') {
      const extra: MenuItem[] = forms.map((f) => ({
        title: f.name,
        path: `/workflow-forms-management/forms/${f.id}/submissions`,
        // List page requires view to load submissions; New submission is shown when user also has add.
        permission: 'workflow_forms.submissions.view',
      }));
      return {
        ...item,
        children: [...(item.children || []), ...extra],
      };
    }
    if (item.children?.length) {
      return { ...item, children: injectPublishedWorkflowForms(item.children, forms) };
    }
    return item;
  });
}
