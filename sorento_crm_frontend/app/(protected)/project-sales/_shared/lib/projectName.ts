/**
 * PROJECT-NAME (owner, 10 Nov): a project, and a lead, may carry a short NAME beside its long
 * legal title. Every place that identifies a project by words shows the name, and the title
 * when there is no name yet (card rule 7). A printed document (letterhead, PDF) keeps the full
 * title and never calls this.
 * Mirrors the backend's `project_display_name`.
 */
export const PROJECT_NAME_MAX_LENGTH = 80;

export function projectDisplayName(project: {
  name?: string | null;
  title?: string | null;
}): string {
  const name = (project.name ?? '').trim();
  if (name) return name;
  return project.title ?? '';
}
