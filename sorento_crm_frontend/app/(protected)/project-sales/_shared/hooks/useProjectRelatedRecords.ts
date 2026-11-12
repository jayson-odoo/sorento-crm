'use client';

import { useQuery } from '@tanstack/react-query';
import { listProjectRelatedRecords } from '../services/projectService';
import type { RelatedRecordsParams } from '../types/project.types';

export const RELATED_RECORDS_KEY = 'project-related-records';

/**
 * PROJECT-RELATED-RECORDS: the project's Related tab rows for these grid params, sorted,
 * searched, filtered and paged on the server. The tab badge reads `type_counts` off the same
 * query (the panel's opening params), so opening the tab costs no second request.
 */
export function useProjectRelatedRecords(
  projectId: string | undefined,
  params: RelatedRecordsParams,
  options: { enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: [RELATED_RECORDS_KEY, projectId, params],
    queryFn: () => listProjectRelatedRecords(projectId as string, params),
    enabled: Boolean(projectId) && (options.enabled ?? true),
    // Keep the page on screen while the next sort, search or page loads.
    placeholderData: (previous) => previous,
  });
}
