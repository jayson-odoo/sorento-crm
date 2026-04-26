'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useMutation, useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogFooter,
  DialogClose,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  createProjectMasterQuotation,
  getCommercialProject,
  getCommercialProjectsAllPages,
} from '@/app/(protected)/commercial-management/projects/services/commercialProjectService';
import { getCommercialLeads } from '@/app/(protected)/commercial/leads/services/leadService';
import CreateProjectDialog from '@/app/(protected)/commercial-management/projects/components/CreateProjectDialog';
import { getWorkflowStages } from '@/app/(protected)/commercial-core/process-configuration/services/workflowStageService';

export type CreateQuotationPreset = {
  projectId: string;
  /** Optional — used only if we need consistency; preset UI uses labels below */
  customerId?: string | null;
  clientLabel: string;
  projectLabel: string;
  /** Used as initial quotation title */
  defaultTitle: string;
};

export interface CreateQuotationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** When set, client & project are fixed (project detail); only Create / Cancel apply */
  preset?: CreateQuotationPreset | null;
  initialCustomerId?: string | null;
  initialProjectId?: string | null;
  initialLeadId?: string | null;
  /** After API success and navigation (preset mode may stay on page) */
  onCreated?: () => void;
}

export function CreateQuotationDialog({
  open,
  onOpenChange,
  preset,
  initialCustomerId,
  initialProjectId,
  initialLeadId,
  onCreated,
}: CreateQuotationDialogProps) {
  const router = useRouter();
  const isPreset = Boolean(preset?.projectId);

  const [projectId, setProjectId] = useState<string>('');
  const [createProjectOpen, setCreateProjectOpen] = useState(false);
  const [projectQuery, setProjectQuery] = useState('');
  const [projectPickerOpen, setProjectPickerOpen] = useState(false);
  const [selectedLeadId, setSelectedLeadId] = useState<string>('');
  const targetProjectId = isPreset ? preset!.projectId : projectId;

  useEffect(() => {
    if (!open) return;
    if (isPreset) {
      setProjectId('');
      setSelectedLeadId(initialLeadId ?? '');
      return;
    }
    setProjectId(initialProjectId ?? '');
    setSelectedLeadId(initialLeadId ?? '');
    setProjectQuery('');
  }, [open, isPreset, initialProjectId, initialLeadId]);

  const {
    data: projectOptions = [],
    isLoading: projectsLoading,
    isFetching: projectsFetching,
  } = useQuery({
    queryKey: ['create-quotation-projects'],
    queryFn: async () => {
      const [allProjects, projectStages] = await Promise.all([
        getCommercialProjectsAllPages({
          searchQuery: '',
          sorting: [],
        }),
        getWorkflowStages({ domain: 'project' }),
      ]);
      const terminalStageIds = new Set(
        (projectStages || []).filter((s) => s.is_terminal).map((s) => s.id),
      );
      return (allProjects.data ?? [])
        .filter((p) => !terminalStageIds.has(p.project_stage_id))
        .map((p) => ({ id: p.id, title: p.title, status: p.status }))
        .sort((a, b) => a.title.localeCompare(b.title))
        .map(({ id, title }) => ({ id, title }));
    },
    enabled: open && !isPreset,
    staleTime: 30_000,
  });

  const { data: projectDetail } = useQuery({
    queryKey: ['create-quotation-project', targetProjectId],
    queryFn: () => getCommercialProject(targetProjectId),
    enabled: open && Boolean(targetProjectId),
  });
  const { data: customerLeads = [] } = useQuery({
    queryKey: ['create-quotation-customer-leads', initialCustomerId],
    queryFn: async () => {
      if (!initialCustomerId) return [];
      const res = await getCommercialLeads({
        pageIndex: 0,
        pageSize: 50,
        sorting: [],
        customer_id: initialCustomerId,
      });
      return res.data ?? [];
    },
    enabled: open && Boolean(initialCustomerId),
  });
  const defaultLeadIdForProjectCreate = initialLeadId || customerLeads[0]?.id || null;
  const { data: leadOptions = [], isLoading: leadsLoading } = useQuery({
    queryKey: ['create-quotation-terminal-leads', open],
    queryFn: async () => {
      const res = await getCommercialLeads({
        pageIndex: 0,
        pageSize: 300,
        sorting: [],
        terminal_pipeline_only: true,
      });
      return (res.data ?? []).map((lead) => ({
        id: lead.id,
        lead_code: lead.lead_code,
        title: lead.title,
        stage_code: lead.stage_code ?? null,
      }));
    },
    enabled: open && isPreset,
    staleTime: 30_000,
  });

  const selectedProjectName = useMemo(() => {
    if (isPreset) return preset?.projectLabel ?? '';
    return projectOptions.find((p) => p.id === projectId)?.title ?? '';
  }, [isPreset, preset?.projectLabel, projectOptions, projectId]);

  const titleForCreate = useMemo(() => {
    if (isPreset && preset?.defaultTitle) return preset.defaultTitle.trim();
    if (selectedProjectName) return `${selectedProjectName} quotation`.trim();
    return 'New quotation';
  }, [isPreset, preset?.defaultTitle, selectedProjectName]);

  const derivedCustomerId = useMemo(() => {
    if (preset?.customerId) return preset.customerId;
    if (initialCustomerId) return initialCustomerId;
    if (projectDetail?.customer_id) return projectDetail.customer_id;
    if (Array.isArray(projectDetail?.customer_ids) && projectDetail.customer_ids.length > 0) {
      return projectDetail.customer_ids[0] || null;
    }
    return null;
  }, [preset?.customerId, initialCustomerId, projectDetail?.customer_id, projectDetail?.customer_ids]);

  const canSubmit = Boolean(targetProjectId) && (!isPreset || Boolean(selectedLeadId));
  const filteredProjectOptions = useMemo(() => {
    const q = projectQuery.trim().toLowerCase();
    if (!q) return projectOptions;
    return projectOptions.filter((p) => (p.title || '').toLowerCase().includes(q));
  }, [projectOptions, projectQuery]);
  const projectNameCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const p of projectOptions) {
      const key = (p.title || '').trim().toLowerCase();
      counts.set(key, (counts.get(key) || 0) + 1);
    }
    return counts;
  }, [projectOptions]);

  const createMut = useMutation({
    mutationFn: async () => {
      const t = titleForCreate || 'New quotation';
      return createProjectMasterQuotation(targetProjectId, {
        title: t,
        valid_until: null,
        description: null,
        remark: null,
        ...(derivedCustomerId ? { customer_id: derivedCustomerId } : {}),
        ...((isPreset ? selectedLeadId : initialLeadId) ? { lead_id: (isPreset ? selectedLeadId : initialLeadId)! } : {}),
      });
    },
    onSuccess: (row) => {
      toast.success('Quotation created');
      onOpenChange(false);
      onCreated?.();
      router.push(
        `/commercial-management/quotation-revisions/edit?tender=${encodeURIComponent(row.tender_code)}&quotation=${encodeURIComponent(row.quotation_code)}&project=${encodeURIComponent(targetProjectId)}`,
      );
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const fieldSurface =
    'flex h-[38px] w-full items-center rounded-[14px] border border-[#d1d5dc] bg-white px-3 text-left text-[16px] text-[#0a0a0a]';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-[448px] gap-0 rounded-2xl border border-[#e5e7eb] p-0 shadow-lg"
        showCloseButton
      >
        <DialogTitle className="sr-only">Create New Quotation</DialogTitle>
        <div className="flex flex-col gap-6 px-6 pb-6 pt-6">
          <h2 className="pr-10 text-xl font-medium leading-7 tracking-tight text-[#0a0a0a]">Create New Quotation</h2>

          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label className="text-[14px] font-medium text-[#4a5565]">
                Project title <span className="text-destructive">*</span>
              </Label>
              {isPreset ? (
                <Textarea
                  value={preset!.projectLabel || '—'}
                  readOnly
                  rows={4}
                  className={`${fieldSurface} h-[112px] resize-none overflow-y-auto whitespace-pre-wrap break-words`}
                />
              ) : (
                <Popover open={projectPickerOpen} onOpenChange={setProjectPickerOpen}>
                  <PopoverTrigger asChild>
                    <Button
                      type="button"
                      variant="outline"
                      className={`${fieldSurface} h-[38px] justify-between font-normal`}
                      disabled={projectsLoading || projectsFetching}
                    >
                      {projectId
                        ? projectOptions.find((p) => p.id === projectId)?.title || 'Select project'
                        : projectsLoading || projectsFetching
                          ? 'Loading projects...'
                          : projectOptions.length === 0
                            ? 'No projects found'
                            : 'Select project'}
                      <span className="text-[#6a7282]">⌄</span>
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
                    <Command shouldFilter={false}>
                      <CommandInput
                        placeholder="Search project..."
                        value={projectQuery}
                        onValueChange={setProjectQuery}
                      />
                      <CommandList>
                        <CommandEmpty>No matching project.</CommandEmpty>
                        <CommandGroup>
                          {filteredProjectOptions.map((p) => (
                            <CommandItem
                              key={p.id}
                              value={`${p.id} ${p.title}`}
                              onSelect={() => {
                                setProjectId(p.id);
                                setProjectPickerOpen(false);
                              }}
                            >
                              <span className="flex w-full items-center justify-between gap-2">
                                <span>{p.title}</span>
                                {((projectNameCounts.get((p.title || '').trim().toLowerCase()) || 0) > 1) ? (
                                  <span className="text-xs text-[#6a7282]">#{p.id.slice(0, 8)}</span>
                                ) : null}
                              </span>
                            </CommandItem>
                          ))}
                        </CommandGroup>
                      </CommandList>
                    </Command>
                    {filteredProjectOptions.length === 0 ? (
                      <div className="border-t p-2">
                        <Button
                          type="button"
                          variant="outline"
                          className="w-full"
                          onClick={() => {
                            setProjectPickerOpen(false);
                            setCreateProjectOpen(true);
                          }}
                        >
                          + Create project
                        </Button>
                      </div>
                    ) : null}
                  </PopoverContent>
                </Popover>
              )}
            </div>
            {isPreset ? (
              <div className="flex flex-col gap-2">
                <Label className="text-[14px] font-medium text-[#4a5565]">
                  Lead <span className="text-destructive">*</span>
                </Label>
                <Select value={selectedLeadId} onValueChange={setSelectedLeadId} disabled={leadsLoading}>
                  <SelectTrigger className={`${fieldSurface} h-[38px] justify-between`}>
                    <SelectValue placeholder={leadsLoading ? 'Loading leads...' : 'Select lead'} />
                  </SelectTrigger>
                  <SelectContent>
                    {leadOptions.map((lead) => (
                      <SelectItem key={lead.id} value={lead.id}>
                        {lead.lead_code} - {lead.title}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ) : null}
          </div>

          <DialogFooter className="flex-row gap-3 sm:justify-stretch">
            <DialogClose asChild>
              <Button
                type="button"
                variant="outline"
                className="h-[42px] flex-1 rounded-[14px] border-[#d1d5dc] font-medium text-[#0a0a0a]"
              >
                Cancel
              </Button>
            </DialogClose>
            <Button
              type="button"
              className="h-[42px] flex-1 rounded-[14px] bg-[#e7000b] font-medium text-white hover:bg-[#e7000b]/90 disabled:opacity-50"
              disabled={!canSubmit || createMut.isPending}
              onClick={() => createMut.mutate()}
            >
              Create
            </Button>
          </DialogFooter>
        </div>
      </DialogContent>
      <CreateProjectDialog
        open={createProjectOpen}
        onOpenChange={setCreateProjectOpen}
        defaultLeadId={defaultLeadIdForProjectCreate}
        onProjectCreated={(project) => {
          setProjectId(project.id);
          setCreateProjectOpen(false);
        }}
      />
    </Dialog>
  );
}
