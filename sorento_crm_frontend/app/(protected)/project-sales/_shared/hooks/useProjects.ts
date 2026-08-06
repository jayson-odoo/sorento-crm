'use client';

import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
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
  changeLeadStatus,
  createQuotation,
  createQuotationLine,
  createSeries,
  deletePriceFloor,
  deleteQuotation,
  deleteQuotationLine,
  deleteSeries,
  getEffectivePriceFloor,
  listPriceFloors,
  listQuotationLines,
  listQuotationLossReasons,
  listQuotationVersions,
  listQuotations,
  listSeries,
  reviseQuotation,
  setQuotationOutcome,
  updateQuotation,
  replaceQuotationLines,
  updateQuotationLine,
  updateSeries,
  upsertPriceFloor,
  listSamples,
  createSample,
  updateSample,
  deleteSample,
  listPurchaseOrders,
  createPurchaseOrder,
  updatePurchaseOrder,
  deletePurchaseOrder,
  listPurchaseOrderLines,
  createPurchaseOrderLine,
  updatePurchaseOrderLine,
  deletePurchaseOrderLine,
  listProjectSponsorships,
  getSponsorshipRollup,
  getProjectDashboard,
  createLead,
  createParty,
  deleteLead,
  disqualifyLead,
  getCustomerPortfolio,
  getLead,
  getLeadMetrics,
  listDisqualifyReasons,
  listLeads,
  previewQualify,
  qualifyLead,
  reopenLead,
  updateLead,
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
  LeadListParams,
  FloorTargetLevel,
  PriceFloorRuleBody,
  ProjectSampleBody,
  ProjectPurchaseOrderBody,
  PurchaseOrderLineBody,
  ProjectQuotation,
  ProjectQuotationBody,
  ProjectSeriesBody,
  QuotationLineBody,
  QuotationLineBulkItem,
  QuotationOutcomeBody,
  LeadQualifyBody,
  ProjectLeadBody,
  ProjectTemplateBody,
  ProjectTypeBody,
  ProjectTemplateTaskBody,
  ProjectUpdateBody,
  TaskPhase,
  TaskStatusChangeBody,
} from '../types/project.types';
// Keys only, and the document hooks import nothing from here, so the two files do not circle.
import { quotationDocumentsKey } from './useQuotationDocuments';

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
 *
 * `placeholderData` keeps the previous answer on screen while the NEXT one loads, so the
 * panel does not flicker mid-typing - but only while the title is still long enough to ask
 * about. Returning it unconditionally left the candidate list on screen after the field was
 * cleared: an empty title showing "Similar projects" for a name nobody had typed.
 */
const CLASH_MIN_CHARS = 4;

export function useClashPreview(title: string, developerPartyId?: string | null) {
  const trimmed = title.trim();
  const askable = trimmed.length >= CLASH_MIN_CHARS;
  return useQuery({
    queryKey: ['project-clash', trimmed.toLowerCase(), developerPartyId ?? null],
    queryFn: () => previewClashes({ title: trimmed, developer_party_id: developerPartyId }),
    enabled: askable,
    placeholderData: (previous) => (askable ? previous : undefined),
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


// ------------------------------------------------------------------- leads

export const LEADS_KEY = 'project-leads';
export const leadsListKey = (params: LeadListParams) => [LEADS_KEY, 'list', params];
export const leadKey = (leadId: string) => [LEADS_KEY, 'detail', leadId];
export const LEAD_METRICS_KEY = [LEADS_KEY, 'metrics'];
export const LEAD_REASONS_KEY = [LEADS_KEY, 'disqualify-reasons'];
export const customerPortfolioKey = (customerId: string) => [
  LEADS_KEY,
  'portfolio',
  customerId,
];

export function useLeads(params: LeadListParams) {
  return useQuery({ queryKey: leadsListKey(params), queryFn: () => listLeads(params) });
}

export function useLead(leadId: string | undefined) {
  return useQuery({
    queryKey: leadKey(leadId ?? ''),
    queryFn: () => getLead(leadId as string),
    enabled: Boolean(leadId),
  });
}

export function useLeadMetrics() {
  return useQuery({ queryKey: LEAD_METRICS_KEY, queryFn: () => getLeadMetrics() });
}

/**
 * The reasons are admin-configured and change about once a year, so they are cached
 * hard: refetching them on every dialog open is a request that never returns anything
 * new.
 */
export function useDisqualifyReasons() {
  return useQuery({
    queryKey: LEAD_REASONS_KEY,
    queryFn: () => listDisqualifyReasons(),
    staleTime: 10 * 60 * 1000,
  });
}

export function useCustomerPortfolio(customerId: string | undefined) {
  return useQuery({
    queryKey: customerPortfolioKey(customerId ?? ''),
    queryFn: () => getCustomerPortfolio(customerId as string),
    enabled: Boolean(customerId),
  });
}

/**
 * What qualifying would hit. Enabled only on an open lead: previewing a clash for a
 * lead that is already qualified or dead is a question nobody asked.
 */
export function useQualifyPreview(
  leadId: string | undefined,
  params: { title?: string | null; developerPartyId?: string | null; enabled?: boolean },
) {
  const title = (params.title ?? '').trim();
  return useQuery({
    queryKey: [LEADS_KEY, 'qualify-preview', leadId ?? '', title.toLowerCase(), params.developerPartyId ?? null],
    queryFn: () =>
      previewQualify(leadId as string, {
        title: title || null,
        developer_party_id: params.developerPartyId ?? null,
      }),
    enabled: Boolean(leadId) && params.enabled !== false,
    placeholderData: (previous) => previous,
  });
}

/**
 * Lead writes invalidate the PROJECT lists too.
 *
 * Qualifying creates a project, and disqualifying changes the conversion metric that
 * the pipeline header reads. Invalidating only the lead list would leave the pipeline
 * missing the project the user just created.
 */
function useLeadInvalidate() {
  const queryClient = useQueryClient();
  return (leadId?: string) => {
    queryClient.invalidateQueries({ queryKey: [LEADS_KEY] });
    queryClient.invalidateQueries({ queryKey: [PROJECTS_KEY] });
    if (leadId) queryClient.invalidateQueries({ queryKey: leadKey(leadId) });
  };
}

export function useLeadMutations() {
  const invalidate = useLeadInvalidate();

  const create = useMutation({
    mutationFn: (body: ProjectLeadBody) => createLead(body),
    onSuccess: (lead) => {
      invalidate(lead.id);
      toast.success(`${lead.lead_code} recorded`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<ProjectLeadBody> }) =>
      updateLead(id, body),
    onSuccess: (lead) => {
      invalidate(lead.id);
      toast.success('Lead saved');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const move = useMutation({
    mutationFn: ({ id, toStatusId }: { id: string; toStatusId: string }) =>
      changeLeadStatus(id, toStatusId),
    onSuccess: (lead) => {
      invalidate(lead.id);
      toast.success(`${lead.lead_code} moved to ${lead.status_label ?? 'a new stage'}`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const qualify = useMutation({
    mutationFn: ({ id, body }: { id: string; body?: LeadQualifyBody }) =>
      qualifyLead(id, body ?? {}),
    onSuccess: (project) => {
      invalidate();
      toast.success(`${project.project_code} registered from this lead`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const disqualify = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      disqualifyLead(id, reason),
    onSuccess: (lead) => {
      invalidate(lead.id);
      toast.success(`${lead.lead_code} disqualified`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const reopen = useMutation({
    mutationFn: (id: string) => reopenLead(id),
    onSuccess: (lead) => {
      invalidate(lead.id);
      toast.success(`${lead.lead_code} reopened`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteLead(id),
    onSuccess: () => {
      invalidate();
      toast.success('Lead deleted');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { create, update, move, qualify, disqualify, reopen, remove };
}


// -------------------------------------------------------------- quotations

export const QUOTATIONS_KEY = 'project-quotations';
export const quotationsKey = (projectId: string) => [QUOTATIONS_KEY, 'list', projectId];
export const versionsKey = (quotationId: string) => [QUOTATIONS_KEY, 'versions', quotationId];
export const linesKey = (versionId: string) => [QUOTATIONS_KEY, 'lines', versionId];
export const LOSS_REASONS_KEY = [QUOTATIONS_KEY, 'loss-reasons'];
export const SERIES_KEY = ['project-series'];
export const PRICE_FLOORS_KEY = ['project-price-floors'];

export function useQuotations(projectId: string | undefined) {
  return useQuery({
    queryKey: quotationsKey(projectId ?? ''),
    queryFn: () => listQuotations(projectId as string),
    enabled: Boolean(projectId),
  });
}

export function useQuotationVersions(quotationId: string | undefined) {
  return useQuery({
    queryKey: versionsKey(quotationId ?? ''),
    queryFn: () => listQuotationVersions(quotationId as string),
    enabled: Boolean(quotationId),
  });
}

/**
 * Every version of every scope on one project, flattened.
 *
 * The Quotations tab lists REVISIONS, not just the current price per scope: the client's
 * words were "in this list i can see a list of quotation for this project which includes all
 * those revisions". Nothing on the server returns them in one call, so this fans out over the
 * scopes - a handful per project - and react-query dedupes each against the per-quotation key
 * the version editor already uses, so opening a scope below the list costs no extra request.
 */
export function useProjectQuotationVersions(quotations: ProjectQuotation[] | undefined) {
  const list = quotations ?? [];
  const results = useQueries({
    queries: list.map((quotation) => ({
      queryKey: versionsKey(quotation.id),
      queryFn: () => listQuotationVersions(quotation.id),
      staleTime: 30_000,
    })),
  });

  return {
    isLoading: results.some((result) => result.isLoading),
    isError: results.some((result) => result.isError),
    error: results.find((result) => result.error)?.error ?? null,
    rows: list.flatMap((quotation, index) =>
      (results[index]?.data ?? []).map((version) => ({ quotation, version })),
    ),
  };
}

export function useQuotationLines(versionId: string | undefined) {
  return useQuery({
    queryKey: linesKey(versionId ?? ''),
    queryFn: () => listQuotationLines(versionId as string),
    enabled: Boolean(versionId),
  });
}

export function useQuotationLossReasons() {
  return useQuery({
    queryKey: LOSS_REASONS_KEY,
    queryFn: () => listQuotationLossReasons(),
    staleTime: 10 * 60 * 1000,
  });
}

export function useProjectSeries(includeInactive = false) {
  return useQuery({
    queryKey: [...SERIES_KEY, includeInactive],
    queryFn: () => listSeries(includeInactive),
  });
}

export function usePriceFloors() {
  return useQuery({ queryKey: PRICE_FLOORS_KEY, queryFn: () => listPriceFloors() });
}

/**
 * The floor in force for one product or one category.
 *
 * Keyed UNDER `PRICE_FLOORS_KEY` on purpose: every floor write invalidates that prefix,
 * so setting a category floor from the category editor also refreshes what a product
 * under it says it inherits, without either surface having to know about the other.
 */
export function useEffectivePriceFloor(
  target: { level: FloorTargetLevel; id: string } | null,
) {
  return useQuery({
    queryKey: [...PRICE_FLOORS_KEY, 'effective', target?.level, target?.id],
    queryFn: () => getEffectivePriceFloor(target as { level: FloorTargetLevel; id: string }),
    enabled: Boolean(target?.id),
  });
}

/**
 * A quotation write invalidates the PROJECT as well.
 *
 * The project's outcome is derived from its quotations (AC-E10), so winning a scope
 * changes the header, the pipeline card and the board column. Invalidating only the
 * quotation list would leave all three stating the old outcome.
 */
export function useQuotationMutations(projectId: string) {
  const queryClient = useQueryClient();
  const invalidate = (quotationId?: string) => {
    queryClient.invalidateQueries({ queryKey: [QUOTATIONS_KEY] });
    queryClient.invalidateQueries({ queryKey: projectKey(projectId) });
    queryClient.invalidateQueries({ queryKey: [PROJECTS_KEY, 'list'] });
    if (quotationId) queryClient.invalidateQueries({ queryKey: versionsKey(quotationId) });
  };

  const create = useMutation({
    mutationFn: (body: ProjectQuotationBody) => createQuotation(projectId, body),
    onSuccess: (quotation) => {
      invalidate(quotation.id);
      toast.success(`"${quotation.scope_label}" added`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<ProjectQuotationBody> }) =>
      updateQuotation(id, body),
    onSuccess: (quotation) => {
      invalidate(quotation.id);
      toast.success('Quotation saved');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const revise = useMutation({
    mutationFn: (quotationId: string) => reviseQuotation(quotationId),
    onSuccess: (version) => {
      invalidate(version.quotation_id);
      toast.success(`Version ${version.version_no} opened`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const decide = useMutation({
    mutationFn: ({ id, body }: { id: string; body: QuotationOutcomeBody }) =>
      setQuotationOutcome(id, body),
    onSuccess: (quotation) => {
      invalidate(quotation.id);
      toast.success(`"${quotation.scope_label}" marked ${quotation.outcome}`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  // No success toast here: the only caller is a ConfirmDeleteDialog, which raises its
  // own. Toasting in both places puts two notifications on screen for one delete.
  const remove = useMutation({
    mutationFn: (quotationId: string) => deleteQuotation(quotationId),
    onSuccess: () => invalidate(),
  });

  return { create, update, revise, decide, remove };
}

/**
 * Line writes invalidate the lines AND the quotation list: the list carries the version
 * total and the two alert counts, which every line edit can change.
 *
 * And the DOCUMENT, because its letterhead carries the grand total across scopes (AC-D2).
 * That is a different query from the lines, so without this a line edit moved the footer
 * under the money column and left the total at the top of the page reading the old figure -
 * two numbers on one screen disagreeing, which is exactly what makes a reader distrust the
 * arithmetic. Prefix key, so both the document list and the open document refetch.
 */
export function useQuotationLineMutations(projectId: string, versionId: string) {
  const queryClient = useQueryClient();
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: linesKey(versionId) });
    queryClient.invalidateQueries({ queryKey: quotationsKey(projectId) });
    queryClient.invalidateQueries({ queryKey: [QUOTATIONS_KEY, 'versions'] });
    queryClient.invalidateQueries({ queryKey: quotationDocumentsKey(projectId) });
  };

  const create = useMutation({
    mutationFn: (body: QuotationLineBody) => createQuotationLine(versionId, body),
    onSuccess: (line) => {
      invalidate();
      // Only NEWS gets a toast. A line that saved exactly as typed is not news: the row
      // already shows the value, and a toast per blur moves the page under the cursor
      // while somebody is working down a column of twenty lines.
      if (line.is_below_floor) {
        toast.warning(
          `Below the floor of ${line.floor_value_applied}. Management has been notified.`,
        );
      }
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<QuotationLineBody> }) =>
      updateQuotationLine(versionId, id, body),
    onSuccess: (line) => {
      invalidate();
      if (line.is_below_floor) {
        toast.warning(`Below the floor of ${line.floor_value_applied}.`);
      }
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const remove = useMutation({
    mutationFn: (lineId: string) => deleteQuotationLine(versionId, lineId),
    onSuccess: () => {
      invalidate();
      toast.success('Line removed');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { create, update, remove };
}

/**
 * The whole line set of one version in a single write, for the edit view's Save (S10/S11).
 *
 * Separate from `useQuotationLineMutations` because the version is a PAYLOAD field here, not a
 * binding: one Save can cover several scopes, and a hook bound to one version cannot answer for
 * the others. The invalidations are the same set for the same reason - the quotation list carries
 * the version total, and the document's letterhead carries the grand total across scopes.
 */
export function useQuotationBulkLineMutation(projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ versionId, lines }: { versionId: string; lines: QuotationLineBulkItem[] }) =>
      replaceQuotationLines(versionId, lines),
    onSuccess: (_lines, { versionId }) => {
      queryClient.invalidateQueries({ queryKey: linesKey(versionId) });
      queryClient.invalidateQueries({ queryKey: quotationsKey(projectId) });
      queryClient.invalidateQueries({ queryKey: [QUOTATIONS_KEY, 'versions'] });
      queryClient.invalidateQueries({ queryKey: quotationDocumentsKey(projectId) });
    },
    // No toast: the screen raises ONE for the whole Save, and a quotation with four scopes
    // would otherwise stack four notifications for a single button press.
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useSeriesMutations() {
  const queryClient = useQueryClient();
  const invalidate = () => queryClient.invalidateQueries({ queryKey: SERIES_KEY });

  const create = useMutation({
    mutationFn: (body: ProjectSeriesBody) => createSeries(body),
    onSuccess: () => {
      invalidate();
      toast.success('Series created');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<ProjectSeriesBody> }) =>
      updateSeries(id, body),
    onSuccess: () => {
      invalidate();
      toast.success('Series saved');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteSeries(id),
    onSuccess: () => {
      invalidate();
      toast.success('Series deleted');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { create, update, remove };
}

export function usePriceFloorMutations() {
  const queryClient = useQueryClient();
  const invalidate = () => queryClient.invalidateQueries({ queryKey: PRICE_FLOORS_KEY });

  const upsert = useMutation({
    mutationFn: (body: PriceFloorRuleBody) => upsertPriceFloor(body),
    onSuccess: () => {
      invalidate();
      toast.success('Price floor saved');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const remove = useMutation({
    mutationFn: (id: string) => deletePriceFloor(id),
    onSuccess: () => {
      invalidate();
      toast.success('Price floor removed');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { upsert, remove };
}

// ------------------------------------------------------- samples and customer POs

export const SAMPLES_KEY = 'project-samples';
export const POS_KEY = 'project-purchase-orders';
export const samplesKey = (projectId: string) => [SAMPLES_KEY, projectId];
export const poLinesKey = (poId: string) => [POS_KEY, 'lines', poId];

export function useSamples(projectId: string | undefined) {
  return useQuery({
    queryKey: samplesKey(projectId ?? ''),
    queryFn: () => listSamples(projectId as string),
    enabled: Boolean(projectId),
  });
}

export function usePurchaseOrders(projectId: string | undefined) {
  return useQuery({
    queryKey: [POS_KEY, projectId],
    queryFn: () => listPurchaseOrders(projectId as string),
    enabled: Boolean(projectId),
  });
}

export function usePurchaseOrderLines(poId: string | undefined) {
  return useQuery({
    queryKey: poLinesKey(poId ?? ''),
    queryFn: () => listPurchaseOrderLines(poId as string),
    enabled: Boolean(poId),
  });
}

/**
 * A sample write invalidates the QUOTATIONS too: the version a sample hangs off shows a
 * sample count, so recording one changes a panel the user may be looking at.
 */
export function useSampleMutations(projectId: string) {
  const queryClient = useQueryClient();
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: samplesKey(projectId) });
    queryClient.invalidateQueries({ queryKey: quotationsKey(projectId) });
  };

  const create = useMutation({
    mutationFn: (body: ProjectSampleBody) => createSample(projectId, body),
    onSuccess: () => {
      invalidate();
      toast.success('Sample recorded');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<ProjectSampleBody> }) =>
      updateSample(id, body),
    onSuccess: () => {
      invalidate();
      toast.success('Sample saved');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  // No success toast: the only caller is a ConfirmDeleteDialog, which raises its own.
  const remove = useMutation({
    mutationFn: (sampleId: string) => deleteSample(sampleId),
    onSuccess: () => invalidate(),
  });

  return { create, update, remove };
}

/**
 * A PO write invalidates the PROJECT as well: the first PO moves the funnel to PO
 * Received (AC-F10), so the header and the board column change with it.
 */
export function usePurchaseOrderMutations(projectId: string) {
  const queryClient = useQueryClient();
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: [POS_KEY, projectId] });
    queryClient.invalidateQueries({ queryKey: projectKey(projectId) });
    queryClient.invalidateQueries({ queryKey: [PROJECTS_KEY, 'list'] });
  };

  const create = useMutation({
    mutationFn: (body: ProjectPurchaseOrderBody) => createPurchaseOrder(projectId, body),
    onSuccess: (po) => {
      invalidate();
      // Two different truths, and the user needs to know which one happened: the PO is
      // always recorded, the funnel move is not always legal from where the project sits.
      if (po.status_moved_to_po_received) {
        toast.success(`${po.po_number} recorded. The project moved to PO Received.`);
      } else {
        toast.success(`${po.po_number} recorded.`);
      }
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<ProjectPurchaseOrderBody> }) =>
      updatePurchaseOrder(id, body),
    onSuccess: () => {
      invalidate();
      toast.success('Purchase order saved');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const remove = useMutation({
    mutationFn: (poId: string) => deletePurchaseOrder(poId),
    onSuccess: () => invalidate(),
  });

  return { create, update, remove };
}

export function usePurchaseOrderLineMutations(projectId: string, poId: string) {
  const queryClient = useQueryClient();
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: poLinesKey(poId) });
    queryClient.invalidateQueries({ queryKey: [POS_KEY, projectId] });
  };

  const create = useMutation({
    mutationFn: (body: PurchaseOrderLineBody) => createPurchaseOrderLine(poId, body),
    onSuccess: (line) => {
      invalidate();
      // A mismatch is recorded, never refused (AC-F9), so this is information rather
      // than an error -- but it has to be said out loud or nobody looks.
      if (line.model_mismatch) {
        toast.warning('Added. This item is not on the quoted version.');
      } else if (line.price_mismatch) {
        toast.warning(`Added. Quoted at ${line.quoted_unit_price}, ordered at ${line.unit_price}.`);
      }
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<PurchaseOrderLineBody> }) =>
      updatePurchaseOrderLine(poId, id, body),
    onSuccess: () => {
      // Silent, like the quotation editor: a routine save is not news (see create above).
      invalidate();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const remove = useMutation({
    mutationFn: (lineId: string) => deletePurchaseOrderLine(poId, lineId),
    onSuccess: () => invalidate(),
  });

  return { create, update, remove };
}

// ------------------------------------------------------------- sponsorship link

export const SPONSORSHIPS_KEY = 'project-sponsorships';

export function useProjectSponsorships(projectId: string | undefined) {
  return useQuery({
    queryKey: [SPONSORSHIPS_KEY, projectId],
    queryFn: () => listProjectSponsorships(projectId as string),
    enabled: Boolean(projectId),
  });
}

export function useSponsorshipRollup(projectId: string | undefined) {
  return useQuery({
    queryKey: [SPONSORSHIPS_KEY, 'rollup', projectId],
    queryFn: () => getSponsorshipRollup(projectId as string),
    enabled: Boolean(projectId),
  });
}

// ------------------------------------------------------------------- reporting

export function useProjectDashboard() {
  return useQuery({
    queryKey: ['project-dashboard'],
    queryFn: () => getProjectDashboard(),
    staleTime: 60_000,
  });
}
