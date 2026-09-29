'use client';

import { Skeleton } from '@/components/ui/skeleton';
import { useProject } from '../../../_shared/hooks/useProjects';
import { ProjectForm } from '../../../_shared/components/ProjectForm';

/**
 * Loads the project, then renders `ProjectForm` in edit mode - or a read-only
 * refusal when the viewer cannot edit it (AC-PF002, AC-PF008, D8).
 */
export function EditProjectClient({ projectId }: { projectId: string }) {
  const { data: project, isLoading, isError } = useProject(projectId);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (isError || !project) {
    return (
      <p className="rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
        This project could not be loaded.
      </p>
    );
  }

  if (!project.can_edit) {
    return (
      <p className="rounded-lg border border-border bg-muted/40 p-4 text-sm text-muted-foreground">
        You cannot edit this project
      </p>
    );
  }

  return <ProjectForm mode="edit" project={project} />;
}
