import { useQuery } from '@tanstack/react-query';
import { listProjectDocuments } from '../services/projectDocumentService';

/** Query key shared by the Documents tab and the header, so one upload refreshes both. */
export const projectDocumentsKey = (projectId: string) => ['project-documents', projectId] as const;

export function useProjectDocuments(projectId: string, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: projectDocumentsKey(projectId),
    queryFn: () => listProjectDocuments(projectId),
    enabled: options.enabled ?? true,
  });
}
