'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { MY_DOWNLOADS_QUERY_KEY } from '@/services/myDownloadsService';
import {
  createReportView,
  deleteReportView,
  exportReport,
  fetchReportMeta,
  fetchReportViews,
  publishReportView,
  REPORT_META_KEY,
  REPORT_RUN_KEY,
  REPORT_VIEWS_KEY,
  runReport,
  setDefaultReportView,
  type ReportMeta,
  type ReportParamValues,
  type ReportResult,
  type ReportView,
  type ReportViewConfig,
  type ReportViews,
} from '@/services/reportService';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

/**
 * Report hooks (PLAN-reporting-foundation). The report KEY is a parameter throughout:
 * report #2 reuses these unchanged, which is the whole point of the foundation.
 */

export function useReportMeta(reportKey: string) {
  return useQuery<ReportMeta, Error>({
    queryKey: [REPORT_META_KEY, reportKey],
    queryFn: () => fetchReportMeta(reportKey),
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });
}

export function useReportRun(
  reportKey: string,
  params: ReportParamValues,
  view: ReportViewConfig | null,
) {
  return useQuery<ReportResult, Error>({
    ...LIST_QUERY_OPTIONS,
    // The pivot shape is part of the request, so reconfiguring the summary refetches
    // rather than re-deriving on the client (the engine owns every total).
    queryKey: [REPORT_RUN_KEY, reportKey, params, view?.pivot],
    queryFn: () => runReport(reportKey, params, view!),
    enabled: Boolean(view),
    retry: 0,
  });
}

export function useReportViews(reportKey: string) {
  return useQuery<ReportViews, Error>({
    queryKey: [REPORT_VIEWS_KEY, reportKey],
    queryFn: () => fetchReportViews(reportKey),
    staleTime: 60 * 1000,
    retry: 1,
  });
}

export function useReportViewMutations(reportKey: string) {
  const queryClient = useQueryClient();
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: [REPORT_VIEWS_KEY, reportKey] });
  };

  const create = useMutation<ReportView, Error, { name: string; view: ReportViewConfig }>({
    mutationFn: (body) => createReportView(reportKey, body),
    onSuccess: (view) => {
      invalidate();
      toast.success(`View "${view.name}" saved`);
    },
    onError: (error) => toast.error(error.message || 'Failed to save the view'),
  });

  // No toast on success: Delete goes through ConfirmDeleteDialog, which owns them.
  const remove = useMutation<void, Error, string>({
    mutationFn: (id) => deleteReportView(reportKey, id),
    onSuccess: invalidate,
  });

  const publish = useMutation<ReportView, Error, { id: string; isShared: boolean }>({
    mutationFn: ({ id, isShared }) => publishReportView(reportKey, id, isShared),
    onSuccess: (view) => {
      invalidate();
      toast.success(view.is_shared ? `"${view.name}" is now shared` : `"${view.name}" is now private`);
    },
    onError: (error) => toast.error(error.message || 'Failed to publish the view'),
  });

  const setDefault = useMutation<ReportView, Error, string>({
    mutationFn: (id) => setDefaultReportView(reportKey, id),
    onSuccess: (view) => {
      invalidate();
      toast.success(`"${view.name}" is now the default for everyone`);
    },
    onError: (error) => toast.error(error.message || 'Failed to set the default view'),
  });

  return { create, remove, publish, setDefault };
}

export function useReportExport(reportKey: string) {
  const queryClient = useQueryClient();
  return useMutation<
    { download_id: string; filename: string },
    Error,
    { params: ReportParamValues; view: ReportViewConfig }
  >({
    mutationFn: ({ params, view }) => exportReport(reportKey, params, view),
    onSuccess: (result) => {
      // The badge moves on the click rather than on the drawer's next poll.
      queryClient.invalidateQueries({ queryKey: MY_DOWNLOADS_QUERY_KEY });
      toast.success(`${result.filename} is being prepared in My Downloads`);
    },
    onError: (error) => toast.error(error.message || 'Failed to queue the export'),
  });
}
