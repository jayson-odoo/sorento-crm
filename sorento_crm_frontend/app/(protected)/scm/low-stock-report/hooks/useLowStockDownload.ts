'use client';

import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { saveBlobAs } from '@/lib/save-blob';
import {
  ENTITY_DOWNLOADS_QUERY_KEY,
  MY_DOWNLOADS_QUERY_KEY,
  fetchDownloadFile,
  fetchDownloadsForEntity,
} from '@/services/myDownloadsService';
import { exportLowStockReport } from '../services/lowStockReportService';
import type { LowStockRequest } from '../types/lowStockReport.types';

interface Job {
  id: string;
  runId: string;
  filename: string | null | undefined;
}

/**
 * Download on the low stock report page (PLAN-excel-preview-26sep AC-14; owner ruling 26 Sep,
 * Q4): post the export with the page's split and filters, read "Preparing..." while the
 * worker builds the file, then save it with no second click. The file also lands in My
 * Downloads, like every other queued export, and the toast says so.
 *
 * The row is watched through the same per-run downloads read the page's chip uses, every
 * `pollMs` and in a background tab too (D27): a buyer who switches tabs while it builds
 * still gets the file.
 */
export function useLowStockDownload({ pollMs = 1000 }: { pollMs?: number } = {}) {
  const queryClient = useQueryClient();
  const [job, setJob] = useState<Job | null>(null);
  const handled = useRef<string | null>(null);

  const start = useMutation({
    mutationFn: (request: LowStockRequest & { runId: string }) => exportLowStockReport(request),
    onSuccess: (row, request) => {
      queryClient.invalidateQueries({ queryKey: MY_DOWNLOADS_QUERY_KEY });
      queryClient.invalidateQueries({
        queryKey: [...ENTITY_DOWNLOADS_QUERY_KEY, 'reorder_run', request.runId],
      });
      handled.current = null;
      setJob({ id: row.id, runId: request.runId, filename: row.filename });
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to start the low stock report'),
  });

  const watch = useQuery({
    queryKey: ['scm', 'low-stock-report', 'download', job?.id] as const,
    queryFn: () => fetchDownloadsForEntity('reorder_run', (job as Job).runId),
    enabled: job !== null,
    refetchInterval: pollMs,
    refetchIntervalInBackground: true,
    gcTime: 0,
  });

  useEffect(() => {
    if (!job || handled.current === job.id) return;
    const row = watch.data?.downloads.find((d) => d.id === job.id);
    if (!row) return;
    if (row.status === 'failed') {
      handled.current = job.id;
      toast.error(row.error || 'The low stock report could not be prepared.');
      setJob(null);
      return;
    }
    if (row.status !== 'ready') return;
    handled.current = job.id;
    const filename = row.filename || job.filename || 'low-stock-report.xlsx';
    fetchDownloadFile(job.id)
      .then((blob) => {
        saveBlobAs(blob, filename);
        toast.success('Low stock report downloaded. It is also in My Downloads.');
      })
      .catch((error: Error) => toast.error(error.message || 'Could not read the file'))
      .finally(() => {
        queryClient.invalidateQueries({ queryKey: MY_DOWNLOADS_QUERY_KEY });
        setJob(null);
      });
  }, [job, watch.data, queryClient]);

  return {
    start: (request: LowStockRequest & { runId: string }) => start.mutate(request),
    preparing: start.isPending || job !== null,
  };
}
