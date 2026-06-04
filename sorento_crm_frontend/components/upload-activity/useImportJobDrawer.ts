'use client';

/**
 * useImportJobDrawer — bridge for Excel/data import flows (stock, DO, GRN,
 * products, warehouses, SPO).
 *
 * Replaces the per-page LatestImportStatusPanel bar: when a page queues an
 * import job it calls `notifyImportQueued()` so the upload drawer opens and
 * the feed refetches immediately — the new `import_job` session then drives
 * the 5s polling until the job is terminal.
 */

import { useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { UPLOAD_ACTIVITY_QUERY_KEY } from './queryKeys';
import { useUploadManager } from './UploadManagerContext';

export function useImportJobDrawer(): { notifyImportQueued: () => void } {
  const queryClient = useQueryClient();
  const { setDrawerOpen } = useUploadManager();

  const notifyImportQueued = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: UPLOAD_ACTIVITY_QUERY_KEY });
    setDrawerOpen(true);
  }, [queryClient, setDrawerOpen]);

  return { notifyImportQueued };
}
