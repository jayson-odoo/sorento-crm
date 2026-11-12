'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { setRecordProject, type RecordProjectKind } from '@/services/recordProjectService';
import { RELATED_RECORDS_KEY } from '@/app/(protected)/project-sales/_shared/hooks/useProjectRelatedRecords';

/** PROJECT-RELATED-RECORDS D2: change a record's Project field from its own page. */
export function useSetRecordProject(kind: RecordProjectKind, recordId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (projectId: string | null) => setRecordProject(kind, recordId, projectId),
    onSuccess: () => {
      // The project pages' Related tabs (old and new project) list this record.
      void queryClient.invalidateQueries({ queryKey: [RELATED_RECORDS_KEY] });
      toast.success('Project saved');
    },
    onError: (error: Error) => toast.error(error.message),
  });
}
