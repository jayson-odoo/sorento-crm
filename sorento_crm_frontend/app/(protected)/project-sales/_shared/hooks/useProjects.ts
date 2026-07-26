'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  addStakeholder,
  changeProjectStatus,
  changeTaskStatus,
  createProjectTask,
  createTemplateTask,
  deleteProjectTask,
  deleteTemplateTask,
  getTaskHistory,
  listMyTasks,
  listProjectTasks,
  listTemplateTasks,
  updateProjectTask,
  updateTemplateTask,
  createParty,
  createProjectTemplate,
  createProjectType,
  deleteProjectTemplate,
  deleteProjectType,
  updateProjectTemplate,
  updateProjectType,
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
  ProjectTaskBody,
  ProjectTemplateBody,
  ProjectTypeBody,
  ProjectTemplateTaskBody,
  ProjectUpdateBody,
  TaskPhase,
  TaskStatusChangeBody,
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

// ------------------------------------------------------------------- tasks

export const tasksKey = (projectId: string, phase?: TaskPhase) => [
  PROJECTS_KEY,
  'tasks',
  projectId,
  phase ?? 'all',
];
export const MY_TASKS_KEY = 'my-tasks';
export const taskHistoryKey = (projectId: string, taskId: string) => [
  PROJECTS_KEY,
  'task-history',
  projectId,
  taskId,
];
export const templateTasksKey = (templateId: string) => ['project-template-tasks', templateId];

export function useProjectTasks(projectId: string | undefined, phase?: TaskPhase) {
  return useQuery({
    queryKey: tasksKey(projectId ?? '', phase),
    queryFn: () => listProjectTasks(projectId as string, phase),
    enabled: Boolean(projectId),
  });
}

export function useMyTasks(params: {
  include_unassigned_owned?: boolean;
  page?: number;
  limit?: number;
}) {
  return useQuery({
    queryKey: [MY_TASKS_KEY, params],
    queryFn: () => listMyTasks(params),
  });
}

export function useTaskHistory(projectId: string, taskId: string | null) {
  return useQuery({
    queryKey: taskHistoryKey(projectId, taskId ?? ''),
    queryFn: () => getTaskHistory(projectId, taskId as string),
    enabled: Boolean(taskId),
  });
}

/**
 * Every task write invalidates the PROJECT too.
 *
 * The project's next action is derived from its earliest open task (AC-N6), so
 * completing a task changes the project row the pipeline renders. Without this the
 * board keeps showing a next action that has already been dealt with.
 */
export function useTaskMutations(projectId: string) {
  const queryClient = useQueryClient();
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: [PROJECTS_KEY, 'tasks', projectId] });
    queryClient.invalidateQueries({ queryKey: projectKey(projectId) });
    queryClient.invalidateQueries({ queryKey: [PROJECTS_KEY, 'list'] });
    queryClient.invalidateQueries({ queryKey: [MY_TASKS_KEY] });
  };

  const create = useMutation({
    mutationFn: (body: ProjectTaskBody) => createProjectTask(projectId, body),
    onSuccess: () => {
      invalidate();
      toast.success('Task added');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<ProjectTaskBody> }) =>
      updateProjectTask(projectId, id, body),
    onSuccess: () => {
      invalidate();
      toast.success('Task saved');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const move = useMutation({
    mutationFn: ({ id, body }: { id: string; body: TaskStatusChangeBody }) =>
      changeTaskStatus(projectId, id, body),
    onSuccess: (task) => {
      invalidate();
      queryClient.invalidateQueries({ queryKey: taskHistoryKey(projectId, task.id) });
      toast.success(`"${task.name}" moved to ${task.status_label ?? 'a new status'}`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteProjectTask(projectId, id),
    onSuccess: () => {
      invalidate();
      toast.success('Task deleted');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { create, update, move, remove };
}

export function useTemplateTasks(templateId: string | undefined) {
  return useQuery({
    queryKey: templateTasksKey(templateId ?? ''),
    queryFn: () => listTemplateTasks(templateId as string),
    enabled: Boolean(templateId),
  });
}

export function useTemplateTaskMutations(templateId: string) {
  const queryClient = useQueryClient();
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: templateTasksKey(templateId) });

  const create = useMutation({
    mutationFn: (body: ProjectTemplateTaskBody) => createTemplateTask(templateId, body),
    onSuccess: () => {
      invalidate();
      toast.success('Checklist item added');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<ProjectTemplateTaskBody> }) =>
      updateTemplateTask(templateId, id, body),
    onSuccess: () => {
      invalidate();
      toast.success('Checklist item saved');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteTemplateTask(templateId, id),
    onSuccess: () => {
      invalidate();
      toast.success('Checklist item removed');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { create, update, remove };
}


// -------------------------------------------------- types / templates admin

/**
 * A type or template write invalidates BOTH lists.
 *
 * Deleting a type orphans nothing (the server refuses while templates exist) but
 * renaming one changes the label every template row shows, and creating a template
 * changes the type's template_count. Invalidating one list only leaves the other
 * disagreeing on screen.
 */
function useConfigInvalidate() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: PROJECT_TYPES_KEY });
    queryClient.invalidateQueries({ queryKey: ['project-templates'] });
  };
}

export function useProjectTypeMutations() {
  const invalidate = useConfigInvalidate();

  const create = useMutation({
    mutationFn: (body: ProjectTypeBody) => createProjectType(body),
    onSuccess: () => {
      invalidate();
      toast.success('Project type created');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<ProjectTypeBody> }) =>
      updateProjectType(id, body),
    onSuccess: () => {
      invalidate();
      toast.success('Project type saved');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteProjectType(id),
    onSuccess: () => {
      invalidate();
      toast.success('Project type deleted');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { create, update, remove };
}

export function useProjectTemplateMutations() {
  const invalidate = useConfigInvalidate();

  const create = useMutation({
    mutationFn: (body: ProjectTemplateBody) => createProjectTemplate(body),
    onSuccess: () => {
      invalidate();
      toast.success('Template created');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<ProjectTemplateBody> }) =>
      updateProjectTemplate(id, body),
    onSuccess: () => {
      invalidate();
      toast.success('Template saved');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteProjectTemplate(id),
    onSuccess: () => {
      invalidate();
      toast.success('Template deleted');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { create, update, remove };
}
