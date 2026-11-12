'use client';

/**
 * Project import: reads and writes (PLAN-project-import-12nov.md, "Frontend contract").
 * Layering: UI -> THESE hooks -> `projectImportService` -> lib/api-client -> backend.
 * Every write invalidates what it changed and toasts; a failure toasts the server's message.
 */
import * as React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { DataGridParamsInput } from '@/lib/api-client';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import { toast } from '@/lib/toast';
import { getUsersSelect } from '@/services/userSelectService';
import { projectCodeLabel } from '../lib/projectCode';
import { projectDisplayName } from '../lib/projectName';
import { listProjects } from '../services/projectService';
import { useFetchCustomerOptions, useFetchPartyOptions } from './useProjects';
import {
  bulkSetLines,
  createRun,
  getLinesSummary,
  getRun,
  listLines,
  listRows,
  listRuns,
  previewRun,
  saveColumns,
  setLine,
  startImport,
} from '../services/projectImportService';
import type {
  ProjectImportBulkBody,
  ProjectImportKind,
  ProjectImportLineBody,
} from '../types/projectImport.types';

export const PROJECT_IMPORT_RUNS_KEY = 'project-import-runs';
export const PROJECT_IMPORT_RUN_KEY = 'project-import-run';
export const PROJECT_IMPORT_LINES_KEY = 'project-import-lines';
export const PROJECT_IMPORT_SUMMARY_KEY = 'project-import-lines-summary';
export const PROJECT_IMPORT_ROWS_KEY = 'project-import-rows';

function failed(error: unknown, fallback: string) {
  toast.error(error instanceof Error && error.message ? error.message : fallback);
}

export function useProjectImportRuns(
  grid: DataGridParamsInput,
  filters: { status?: string[]; uploaded_by?: string[] } = {},
) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [PROJECT_IMPORT_RUNS_KEY, grid, filters],
    queryFn: () => listRuns(grid, filters),
  });
}

export function useProjectImportRun(runId: string | undefined) {
  return useQuery({
    queryKey: [PROJECT_IMPORT_RUN_KEY, runId],
    queryFn: () => getRun(runId as string),
    enabled: Boolean(runId),
    // While the worker imports, re-read until the run says where it ended.
    refetchInterval: (query) => (query.state.data?.status === 'importing' ? 2000 : false),
  });
}

export function useProjectImportLines(
  runId: string,
  kind: ProjectImportKind,
  grid: DataGridParamsInput,
  filters: { status?: 'todo' | 'set' } = {},
) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [PROJECT_IMPORT_LINES_KEY, runId, kind, grid, filters],
    queryFn: () => listLines(runId, kind, grid, filters),
  });
}

export function useProjectImportLinesSummary(runId: string) {
  return useQuery({
    queryKey: [PROJECT_IMPORT_SUMMARY_KEY, runId],
    queryFn: () => getLinesSummary(runId),
  });
}

export function useProjectImportRows(
  runId: string,
  grid: DataGridParamsInput,
  filters: { outcome?: string[]; code?: string[]; sheet?: string[] } = {},
) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [PROJECT_IMPORT_ROWS_KEY, runId, grid, filters],
    queryFn: () => listRows(runId, grid, filters),
  });
}

export function useProjectImportMutations(runId?: string) {
  const qc = useQueryClient();
  const refreshRun = () => {
    void qc.invalidateQueries({ queryKey: [PROJECT_IMPORT_RUN_KEY, runId] });
    void qc.invalidateQueries({ queryKey: [PROJECT_IMPORT_RUNS_KEY] });
  };
  const refreshLines = () => {
    void qc.invalidateQueries({ queryKey: [PROJECT_IMPORT_LINES_KEY, runId] });
    void qc.invalidateQueries({ queryKey: [PROJECT_IMPORT_SUMMARY_KEY, runId] });
  };

  const create = useMutation({
    mutationFn: (file: File) => createRun(file),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [PROJECT_IMPORT_RUNS_KEY] });
      toast.success('File uploaded');
    },
    onError: (error) => failed(error, 'The file could not be uploaded'),
  });

  const columns = useMutation({
    mutationFn: (body: { sheets: string[]; columns: Record<string, string> }) =>
      saveColumns(runId as string, body),
    onSuccess: () => {
      refreshRun();
      refreshLines();
      toast.success('Columns saved');
    },
    onError: (error) => failed(error, 'Failed to save the columns'),
  });

  const line = useMutation({
    mutationFn: (body: ProjectImportLineBody) => setLine(runId as string, body),
    onSuccess: () => {
      refreshLines();
      toast.success('Value saved');
    },
    onError: (error) => failed(error, 'Failed to save the value'),
  });

  const bulk = useMutation({
    mutationFn: (body: ProjectImportBulkBody) => bulkSetLines(runId as string, body),
    onSuccess: (_data, body) => {
      refreshLines();
      toast.success(`${body.keys.length} values saved`);
    },
    onError: (error) => failed(error, 'Failed to save the values'),
  });

  const preview = useMutation({
    mutationFn: () => previewRun(runId as string),
    onSuccess: () => {
      refreshRun();
      void qc.invalidateQueries({ queryKey: [PROJECT_IMPORT_ROWS_KEY, runId] });
      toast.success('Preview ready');
    },
    onError: (error) => failed(error, 'The preview could not run'),
  });

  const importRun = useMutation({
    mutationFn: () => startImport(runId as string),
    onSuccess: () => {
      refreshRun();
      toast.success('Import started');
    },
    onError: (error) => failed(error, 'The import could not start'),
  });

  return { create, columns, line, bulk, preview, importRun };
}

/**
 * The record pickers of the Values step, by kind. The same fetchers the register form uses
 * (`useFetchCustomerOptions`, `useFetchPartyOptions`), projects by code or title, users from
 * `userSelectService`.
 */
export function useLineTargetOptions(kind: ProjectImportKind) {
  const customers = useFetchCustomerOptions();
  const parties = useFetchPartyOptions('developer');
  return React.useCallback(
    async (query: string): Promise<{ value: string; label: string; description?: string }[]> => {
      if (kind === 'customer') return customers(query);
      if (kind === 'developer') return parties(query);
      if (kind === 'person') {
        return (await getUsersSelect({ query })).map((u) => ({ value: u.id, label: u.name ?? '' }));
      }
      const body = await listProjects({ query: query || undefined, approved_only: true, limit: 20 });
      return body.data.map((project) => ({
        value: project.id,
        label: projectDisplayName(project),
        description: projectCodeLabel(project),
      }));
    },
    [customers, kind, parties],
  );
}
