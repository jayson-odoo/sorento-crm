import { useQuery, useQueryClient, useMutation, type UseQueryOptions } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';
import type { CommercialProjectListRow } from '../types/commercialProject.types';
import {
  getCommercialProjects,
  getCommercialProject,
  createCommercialProject,
  updateCommercialProject,
  deleteCommercialProject,
  listProjectTaskTemplates,
} from '../services/commercialProjectService';

type ProjectsListParams = DataGridApiFetchParams & {
  owner_user_id?: string;
  status?: string;
  project_stage_id?: string;
};

export function useCommercialProjects(
  params: ProjectsListParams,
  options?: Pick<UseQueryOptions<DataGridApiResponse<CommercialProjectListRow>>, 'enabled'>,
) {
  return useQuery({
    queryKey: [
      'commercial-projects',
      params.pageIndex,
      params.pageSize,
      params.searchQuery,
      params.owner_user_id,
      params.status,
      params.project_stage_id,
    ],
    queryFn: () => getCommercialProjects(params),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    retry: 1,
    enabled: options?.enabled ?? true,
  });
}

export function useCommercialProject(id: string | null) {
  return useQuery({
    queryKey: ['commercial-project', id],
    queryFn: () => {
      if (!id) throw new Error('Project id required');
      return getCommercialProject(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useProjectTaskTemplates() {
  return useQuery({
    queryKey: ['commercial-project-task-templates'],
    queryFn: () => listProjectTaskTemplates(),
    staleTime: 60_000,
  });
}

export type CommercialProjectUpdateBody = Parameters<typeof updateCommercialProject>[1];

export function useCreateCommercialProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createCommercialProject,
    onSuccess: () => {
      toast.success('Project created');
      void qc.invalidateQueries({ queryKey: ['commercial-projects'] });
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useUpdateCommercialProject(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CommercialProjectUpdateBody) => updateCommercialProject(projectId, body),
    onSuccess: (_data, body) => {
      const isTaskBoardOnlyUpdate =
        Object.keys(body || {}).length === 1 && Object.prototype.hasOwnProperty.call(body || {}, 'task_board');
      if (!isTaskBoardOnlyUpdate) {
        toast.success('Project updated');
      }
      void qc.invalidateQueries({ queryKey: ['commercial-projects'] });
      void qc.invalidateQueries({ queryKey: ['commercial-project', projectId] });
    },
    onError: () => toast.error('Update failed'),
  });
}

export function useDeleteCommercialProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteCommercialProject,
    onSuccess: () => {
      toast.success('Project deleted');
      void qc.invalidateQueries({ queryKey: ['commercial-projects'] });
    },
    onError: (e: Error) => toast.error(e.message || 'Delete failed'),
  });
}
