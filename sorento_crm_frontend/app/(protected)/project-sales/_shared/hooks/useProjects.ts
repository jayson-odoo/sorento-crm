'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  addStakeholder,
  changeProjectStatus,
  createParty,
  createTakeoverRequest,
  decideTakeoverRequest,
  deleteParty,
  deleteProject,
  getProject,
  listCollaborators,
  listParties,
  listProjectTemplates,
  listProjectTypes,
  listProjects,
  listStakeholders,
  listTakeoverRequests,
  previewClashes,
  registerProject,
  removeStakeholder,
  updateParty,
  updateProject,
  updateStakeholder,
} from '../services/projectService';
import type {
  ProjectListParams,
  ProjectPartyBody,
  ProjectRegisterBody,
  ProjectStakeholderBody,
  ProjectUpdateBody,
} from '../types/project.types';

export const PROJECTS_KEY = 'projects';
export const PARTIES_KEY = 'project-parties';
export const PROJECT_TYPES_KEY = ['project-types'];

export const projectsListKey = (params: ProjectListParams) => [PROJECTS_KEY, 'list', params];
export const projectKey = (projectId: string) => [PROJECTS_KEY, 'detail', projectId];
export const stakeholdersKey = (projectId: string) => [PROJECTS_KEY, 'stakeholders', projectId];
export const collaboratorsKey = (projectId: string) => [PROJECTS_KEY, 'collaborators', projectId];
export const takeoverKey = (projectId: string) => [PROJECTS_KEY, 'takeover', projectId];

export function useProjects(params: ProjectListParams) {
  return useQuery({
    queryKey: projectsListKey(params),
    queryFn: () => listProjects(params),
  });
}

export function useProject(projectId: string | undefined) {
  return useQuery({
    queryKey: projectKey(projectId ?? ''),
    queryFn: () => getProject(projectId as string),
    enabled: Boolean(projectId),
  });
}

export function useProjectTypes() {
  return useQuery({ queryKey: PROJECT_TYPES_KEY, queryFn: () => listProjectTypes() });
}

export function useProjectTemplates(typeId?: string) {
  return useQuery({
    queryKey: ['project-templates', typeId ?? null],
    queryFn: () => listProjectTemplates(typeId),
  });
}

export function useProjectParties(params: {
  party_type?: string;
  query?: string;
  page?: number;
  limit?: number;
  include_inactive?: boolean;
}) {
  return useQuery({ queryKey: [PARTIES_KEY, params], queryFn: () => listParties(params) });
}

export function useStakeholders(projectId: string | undefined) {
  return useQuery({
    queryKey: stakeholdersKey(projectId ?? ''),
    queryFn: () => listStakeholders(projectId as string),
    enabled: Boolean(projectId),
  });
}

export function useCollaborators(projectId: string | undefined) {
  return useQuery({
    queryKey: collaboratorsKey(projectId ?? ''),
    queryFn: () => listCollaborators(projectId as string),
    enabled: Boolean(projectId),
  });
}

export function useTakeoverRequests(projectId: string | undefined) {
  return useQuery({
    queryKey: takeoverKey(projectId ?? ''),
    queryFn: () => listTakeoverRequests(projectId as string),
    enabled: Boolean(projectId),
  });
}

/**
 * Live clash check as the title is typed.
 *
 * `enabled` on a minimum length, because two characters match half the pipeline and
 * a warning that fires on every keystroke is noise the user learns to ignore.
 * `placeholderData` keeps the previous answer on screen while the next one loads so
 * the panel does not flicker between states mid-typing.
 */
export function useClashPreview(title: string, developerPartyId?: string | null) {
  const trimmed = title.trim();
  return useQuery({
    queryKey: ['project-clash', trimmed.toLowerCase(), developerPartyId ?? null],
    queryFn: () => previewClashes({ title: trimmed, developer_party_id: developerPartyId }),
    enabled: trimmed.length >= 4,
    placeholderData: (previous) => previous,
    staleTime: 30_000,
  });
}

function useInvalidateProjects() {
  const queryClient = useQueryClient();
  return (projectId?: string) => {
    queryClient.invalidateQueries({ queryKey: [PROJECTS_KEY] });
    if (projectId) queryClient.invalidateQueries({ queryKey: projectKey(projectId) });
  };
}

export function useRegisterProject() {
  const invalidate = useInvalidateProjects();
  return useMutation({
    mutationFn: (body: ProjectRegisterBody) => registerProject(body),
    onSuccess: (project) => {
      invalidate();
      toast.success(`${project.project_code} registered`);
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useUpdateProject(projectId: string) {
  const invalidate = useInvalidateProjects();
  return useMutation({
    mutationFn: (body: ProjectUpdateBody) => updateProject(projectId, body),
    onSuccess: () => {
      invalidate(projectId);
      toast.success('Project saved');
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

/**
 * A rejected move must put the card back where it was, so the caller re-reads the
 * list rather than trusting its optimistic position (AC-G3).
 */
export function useChangeProjectStatus() {
  const invalidate = useInvalidateProjects();
  return useMutation({
    mutationFn: ({ projectId, toStatusId }: { projectId: string; toStatusId: string }) =>
      changeProjectStatus(projectId, toStatusId),
    onSuccess: (project) => {
      invalidate(project.id);
      toast.success(`${project.project_code} moved to ${project.status_label ?? 'a new stage'}`);
    },
    onError: (error: Error, variables) => {
      invalidate(variables.projectId);
      toast.error(error.message);
    },
  });
}

export function useDeleteProject() {
  const invalidate = useInvalidateProjects();
  return useMutation({
    mutationFn: (projectId: string) => deleteProject(projectId),
    onSuccess: () => {
      invalidate();
      toast.success('Project deleted');
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useStakeholderMutations(projectId: string) {
  const queryClient = useQueryClient();
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: stakeholdersKey(projectId) });

  const add = useMutation({
    mutationFn: (body: ProjectStakeholderBody) => addStakeholder(projectId, body),
    onSuccess: () => {
      invalidate();
      toast.success('Stakeholder added');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<ProjectStakeholderBody> }) =>
      updateStakeholder(projectId, id, body),
    onSuccess: () => {
      invalidate();
      toast.success('Stakeholder saved');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const remove = useMutation({
    mutationFn: (id: string) => removeStakeholder(projectId, id),
    onSuccess: () => {
      invalidate();
      toast.success('Stakeholder removed');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { add, update, remove };
}

export function usePartyMutations() {
  const queryClient = useQueryClient();
  const invalidate = () => queryClient.invalidateQueries({ queryKey: [PARTIES_KEY] });

  const create = useMutation({
    mutationFn: (body: ProjectPartyBody) => createParty(body),
    onSuccess: (party) => {
      invalidate();
      toast.success(`${party.name} added`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<ProjectPartyBody> }) =>
      updateParty(id, body),
    onSuccess: () => {
      invalidate();
      toast.success('Party saved');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteParty(id),
    onSuccess: () => {
      invalidate();
      toast.success('Party deleted');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { create, update, remove };
}

export function useTakeoverMutations(projectId: string) {
  const queryClient = useQueryClient();
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: takeoverKey(projectId) });
    queryClient.invalidateQueries({ queryKey: collaboratorsKey(projectId) });
    queryClient.invalidateQueries({ queryKey: projectKey(projectId) });
  };

  const request = useMutation({
    mutationFn: (body: { kind: 'join' | 'dispute'; reason: string }) =>
      createTakeoverRequest(projectId, body),
    onSuccess: (created) => {
      invalidate();
      toast.success(
        created.kind === 'join'
          ? 'Request sent to the project owner'
          : 'Dispute raised with the sales manager',
      );
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const decide = useMutation({
    mutationFn: ({
      id,
      approve,
      note,
    }: {
      id: string;
      approve: boolean;
      note?: string | null;
    }) => decideTakeoverRequest(projectId, id, { approve, decision_note: note }),
    onSuccess: (decided) => {
      invalidate();
      toast.success(decided.status === 'approved' ? 'Request approved' : 'Request rejected');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { request, decide };
}
