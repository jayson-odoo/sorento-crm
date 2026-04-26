'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useSession } from 'next-auth/react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  ChevronDown,
  Copy,
  MoreVertical,
  Pencil,
  Plus,
  GripVertical,
  Star,
  Tag,
  Trash2,
  Undo2,
  UserRound,
  UserPlus,
  X,
} from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { masterQuotationDisplayCode } from '@/app/(protected)/commercial-management/quotations/lib/masterQuotationDisplayCode';
import { Textarea } from '@/components/ui/textarea';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { useHasPermission } from '@/hooks/usePermissions';
import { useListBoardViewPreference } from '@/hooks/useListBoardViewPreference';
import { ListBoardViewToggle } from '@/components/common/ListBoardViewToggle';
import {
  useCommercialProject,
  useDeleteCommercialProject,
  useUpdateCommercialProject,
} from '../hooks/useCommercialProjects';
import {
  applyProjectTaskBoardSchedule,
  duplicateCommercialProject,
  duplicateMasterQuotation,
  listProjectMasterQuotations,
  previewProjectTaskBoardSchedule,
  shareProjectOwnership,
  disownProject,
} from '../services/commercialProjectService';
import type {
  CommercialProjectMasterQuotationRow,
  CommercialProjectTaskBoard,
} from '../types/commercialProject.types';
import { CommercialEntityTaskBoard } from '@/app/(protected)/commercial-management/shared/components/CommercialEntityTaskBoard';
import { EntityActivitiesDock } from '@/app/(protected)/commercial-management/shared/components/EntityActivitiesDock';
import { getWorkflowStages } from '@/app/(protected)/commercial-core/process-configuration/services/workflowStageService';
import type { WorkflowStageRow } from '@/app/(protected)/commercial-core/process-configuration/types/workflowStage.types';
import { apiFetch } from '@/lib/api';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { cn } from '@/lib/utils';
import { formatProjectDisplayCode, projectStageHeaderClass as projectStageHeaderBadgeClass } from '../utils/projectDisplay';
import { ProjectQuotationsKanban } from './ProjectQuotationsKanban';
import { CreateQuotationDialog } from '@/app/(protected)/commercial-management/quotations/components/CreateQuotationDialog';
import {
  deleteLeadRespondContactLink,
  linkLeadRespondContact,
  listRespondWorkspaceSelect,
  listLeadRespondContacts,
  searchRespondContacts,
  updateLeadRespondContactLink,
} from '@/app/(protected)/commercial/leads/services/leadRespondContactsService';
import type { LeadRespondContactRow, RespondContactBrief } from '@/app/(protected)/commercial/leads/types/lead.types';
import { Sortable, SortableItem, SortableItemHandle } from '@/components/ui/sortable';

const Q_LINK = 'text-[#e7000b] font-medium hover:underline';
const Q_TH = 'h-11 border-b border-[#e5e7eb] bg-[#f9fafb] text-left text-xs font-medium uppercase tracking-wide text-[#6a7282]';

function quotationStageBadgeClass(stageCode: string | null | undefined): string {
  const c = (stageCode || '').toLowerCase();
  if (c.includes('lost') || c.includes('reject') || c.includes('cancel')) return 'bg-[#ffe2e2] text-[#9f0712]';
  if (c.includes('won') || c.includes('accept') || c.includes('approved')) return 'bg-[#dcfce7] text-[#016630]';
  if (c.includes('draft') || c.includes('prep')) return 'bg-zinc-100 text-zinc-700';
  return 'bg-[#dbeafe] text-[#1447e6]';
}

function formatQuotationListDate(iso: string | undefined | null): string {
  if (!iso) return '—';
  try {
    return new Intl.DateTimeFormat('en-GB', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    }).format(new Date(iso));
  } catch {
    return '—';
  }
}

function qualStr(q: Record<string, unknown>, key: string): string {
  const v = q[key];
  if (v == null || v === '') return '';
  return String(v).trim();
}

function buildLeadAddressOneLine(q: Record<string, unknown>): string {
  const parts = [
    qualStr(q, 'address_line_1'),
    qualStr(q, 'address_line_2'),
    qualStr(q, 'city'),
    qualStr(q, 'postcode'),
    qualStr(q, 'state'),
    qualStr(q, 'country'),
  ].filter(Boolean);
  return parts.length ? parts.join(', ') : '';
}

function formatDisplayDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    return new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date(iso));
  } catch {
    return '—';
  }
}

function initialsFromName(name: string | null | undefined): string {
  const s = (name || '').trim();
  if (!s) return '?';
  const parts = s.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return `${parts[0]!.slice(0, 1)}${parts[1]!.slice(0, 1)}`.toUpperCase();
  return s.slice(0, 2).toUpperCase();
}

function formatAmountByCurrency(rec: Record<string, string> | undefined): string {
  if (!rec || Object.keys(rec).length === 0) return '—';
  return Object.entries(rec)
    .map(([c, a]) => `${a} ${c}`)
    .join(' · ');
}

function contactLabel(row: LeadRespondContactRow): string {
  const c = row.contact;
  const label = [c.first_name, c.last_name].filter(Boolean).join(' ').trim() || c.name || 'Contact';
  return `${label} (${c.phone_number || '—'})`;
}

function searchHitLabel(hit: RespondContactBrief): string {
  const label = [hit.first_name, hit.last_name].filter(Boolean).join(' ').trim() || hit.name || 'Contact';
  return `${label} (${hit.phone_number || '—'})`;
}

export default function ProjectDetail({ projectId }: { projectId: string }) {
  const router = useRouter();
  const { data: session } = useSession();
  const queryClient = useQueryClient();
  const { data, isLoading } = useCommercialProject(projectId);
  const updateMut = useUpdateCommercialProject(projectId);
  const deleteMut = useDeleteCommercialProject();
  const canEditProject = useHasPermission('commercial_core.projects.edit');
  const canShareOwnership = useHasPermission('commercial_core.projects.share_ownership');
  const canDuplicateProject = useHasPermission('commercial_core.projects.add');
  const canViewQuotations = useHasPermission('commercial_core.master_quotations.view');
  const canAddQuotations = useHasPermission('commercial_core.master_quotations.add');
  const [mainTab, setMainTab] = useState('overview');
  const [memberRows, setMemberRows] = useState<{ name: string; tags: string[] }[]>([]);
  const [memberRoleDraft, setMemberRoleDraft] = useState<Record<number, string>>({});
  const [memberDialogOpen, setMemberDialogOpen] = useState(false);
  const [pendingMemberName, setPendingMemberName] = useState('');
  const [respondContactDialogOpen, setRespondContactDialogOpen] = useState(false);
  const [respondContactSearchOpen, setRespondContactSearchOpen] = useState(false);
  const [respondContactSearch, setRespondContactSearch] = useState('');
  const [respondContactSearchDebounced, setRespondContactSearchDebounced] = useState('');
  const [pickedRespondContactId, setPickedRespondContactId] = useState<string | null>(null);
  const [pickedRespondContactLabel, setPickedRespondContactLabel] = useState('');
  const [editingRespondLink, setEditingRespondLink] = useState<LeadRespondContactRow | null>(null);
  const [markAsMainRespondContact, setMarkAsMainRespondContact] = useState(false);
  const [showCreateRespondContactDialog, setShowCreateRespondContactDialog] = useState(false);
  const [newRespondWorkspaceId, setNewRespondWorkspaceId] = useState('');
  const [newRespondPhone, setNewRespondPhone] = useState('');
  const [newRespondName, setNewRespondName] = useState('');
  const [newRespondUserType, setNewRespondUserType] = useState('');
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [taskBoard, setTaskBoard] = useState<CommercialProjectTaskBoard>({ tasks: [] });
  const [createQuotationOpen, setCreateQuotationOpen] = useState(false);
  const currentUserId = ((session?.user as { id?: string } | undefined)?.id || '').trim();
  const amOwner = Boolean(currentUserId) && (data?.owner_user_ids || []).includes(currentUserId);

  const { data: projectStages = [] } = useQuery({
    queryKey: ['workflow-stages', 'project'],
    queryFn: () => getWorkflowStages({ domain: 'project' }),
    staleTime: 60_000,
  });

  const { data: projectQuotations = [], isPending: quotationsPending, refetch: refetchProjectQuotations } = useQuery({
    queryKey: ['project-master-quotations', projectId],
    queryFn: () => listProjectMasterQuotations(projectId),
    enabled: !!projectId && canViewQuotations,
  });

  const quotationWorkspaceHref = useCallback(
    (q: CommercialProjectMasterQuotationRow) =>
      `/commercial-management/quotation-revisions?tender=${encodeURIComponent(q.tender_code)}&quotation=${encodeURIComponent(q.quotation_code)}&project=${encodeURIComponent(projectId)}`,
    [projectId],
  );

  const {
    mode: projectQuotationsViewMode,
    setMode: setProjectQuotationsViewMode,
    hydrated: projectQuotationsViewHydrated,
  } = useListBoardViewPreference(`commercial-project-${projectId}-quotations`);

  const { data: leadRespondLinks = [] } = useQuery({
    queryKey: ['commercial-lead-respond-contacts', data?.lead_id],
    queryFn: () => listLeadRespondContacts(data!.lead_id!),
    enabled: !!data?.lead_id,
  });

  const { data: respondSearchHits = [] } = useQuery({
    queryKey: ['project-respond-contact-search', data?.lead_id, respondContactSearchDebounced],
    queryFn: async () => {
      if (!data?.lead_id) return [] as RespondContactBrief[];
      const workspaceId = leadRespondLinks[0]?.contact.respond_workspace_id;
      if (!workspaceId) return [];
      return searchRespondContacts(workspaceId, respondContactSearchDebounced);
    },
    enabled: !!respondContactDialogOpen && !showCreateRespondContactDialog,
  });

  const { data: respondWorkspaceOptions = [], isLoading: respondWorkspaceLoading } = useQuery({
    queryKey: ['commercial-respond-workspaces-select'],
    queryFn: listRespondWorkspaceSelect,
    enabled: !!respondContactDialogOpen && showCreateRespondContactDialog,
    staleTime: 60_000,
  });

  const propertyAddressLine = useMemo(() => {
    const parts = [
      data?.address_line_1,
      data?.address_line_2,
      data?.postcode,
      data?.city,
      data?.state,
      data?.country,
    ]
      .map((x) => (x || '').trim())
      .filter(Boolean);
    return parts.length ? parts.join(', ') : null;
  }, [data?.address_line_1, data?.address_line_2, data?.postcode, data?.city, data?.state, data?.country]);

  const activeProjectQuotations = useMemo(
    () =>
      projectQuotations.filter(
        (q) => !(q.quotation_stage?.is_terminal && !q.quotation_stage?.is_cancelled),
      ),
    [projectQuotations],
  );

  const projectSalesOrders = useMemo(
    () =>
      projectQuotations.filter(
        (q) => q.quotation_stage?.is_terminal && !q.quotation_stage?.is_cancelled,
      ),
    [projectQuotations],
  );

  /** Counts for tab labels; billing is 0 until project billing is wired to data. */
  const projectTabCounts = useMemo(
    () => ({
      tasks: taskBoard.tasks?.length ?? 0,
      quotations: canViewQuotations ? activeProjectQuotations.length : 0,
      salesOrders: canViewQuotations ? projectSalesOrders.length : 0,
      billing: 0,
      documents: data?.documents?.length ?? 0,
    }),
    [taskBoard.tasks, canViewQuotations, activeProjectQuotations.length, projectSalesOrders.length, data?.documents],
  );

  useEffect(() => {
    const t = window.setTimeout(() => setRespondContactSearchDebounced(respondContactSearch), 250);
    return () => window.clearTimeout(t);
  }, [respondContactSearch]);

  useEffect(() => {
    if (!data) return;
    const members = data.project_members?.length
      ? data.project_members.map((m) => ({ name: m.name, tags: [...(m.tags || [])] }))
      : [];
    setMemberRows(members);
    setTaskBoard(data.task_board && typeof data.task_board === 'object' ? data.task_board : { tasks: [] });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- narrow deps to avoid resetting the form on every React Query refetch
  }, [projectId, data?.updated_at]);

  const persistTaskBoard = useCallback(
    (next: CommercialProjectTaskBoard) => {
      setTaskBoard(next);
      updateMut.mutate({ task_board: next as unknown as Record<string, unknown> });
    },
    [updateMut],
  );

  const persistProjectMembers = useCallback(
    (nextRows: { name: string; tags: string[] }[]) => {
      setMemberRows(nextRows);
      updateMut.mutate({
        project_members: nextRows.filter((r) => r.name.trim()).map((r) => ({ name: r.name.trim(), tags: r.tags })),
      });
    },
    [updateMut],
  );

  const closeRespondContactDialog = () => {
    setRespondContactDialogOpen(false);
    setRespondContactSearchOpen(false);
    setRespondContactSearch('');
    setRespondContactSearchDebounced('');
    setPickedRespondContactId(null);
    setPickedRespondContactLabel('');
    setEditingRespondLink(null);
    setMarkAsMainRespondContact(false);
    setShowCreateRespondContactDialog(false);
    setNewRespondWorkspaceId('');
    setNewRespondPhone('');
    setNewRespondName('');
    setNewRespondUserType('');
  };

  const saveLeadRespondContactOrder = async (rows: LeadRespondContactRow[]) => {
    if (!data?.lead_id) return;
    await Promise.all(
      rows.map((row, index) =>
        updateLeadRespondContactLink(data.lead_id!, row.id, {
          sort_order: index,
        }),
      ),
    );
  };

  const markLeadRespondContactMain = async (row: LeadRespondContactRow) => {
    if (!data?.lead_id || row.contact_role === 'main') return;
    await updateLeadRespondContactLink(data.lead_id, row.id, { contact_role: 'main' });
    void queryClient.invalidateQueries({ queryKey: ['commercial-lead-respond-contacts', data.lead_id] });
  };

  const submitRespondContactDialog = async () => {
    const contactRole: 'main' | 'stakeholder' = markAsMainRespondContact ? 'main' : 'stakeholder';
    if (!data?.lead_id) return;
    if (showCreateRespondContactDialog) {
      if (!newRespondWorkspaceId) {
        toast.error('Respond workspace is required');
        return;
      }
      if (!newRespondPhone.trim()) {
        toast.error('Phone number is required');
        return;
      }
      const createRes = await apiFetch('/api/user-management/contacts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          respond_workspace_id: newRespondWorkspaceId,
          phone_number: newRespondPhone.trim(),
          name: newRespondName.trim() || null,
          user_type: newRespondUserType.trim() || null,
        }),
      });
      if (!createRes.ok) {
        const err = await createRes.json().catch(() => ({}));
        throw new Error((err as { detail?: string; message?: string }).detail || (err as { message?: string }).message || 'Failed to create contact');
      }
      const created = (await createRes.json()) as { id: string; name?: string | null; phone_number?: string | null };
      await linkLeadRespondContact(data.lead_id, {
        respond_contact_id: created.id,
        contact_role: contactRole,
      });
      closeRespondContactDialog();
      void queryClient.invalidateQueries({ queryKey: ['commercial-lead-respond-contacts', data.lead_id] });
      return;
    }
    if (!pickedRespondContactId) return;
    if (editingRespondLink) {
      if (pickedRespondContactId !== editingRespondLink.respond_contact_id) {
        await linkLeadRespondContact(data.lead_id, {
          respond_contact_id: pickedRespondContactId,
          contact_role: contactRole,
          sort_order: editingRespondLink.sort_order,
        });
        await deleteLeadRespondContactLink(data.lead_id, editingRespondLink.id);
      } else {
        await updateLeadRespondContactLink(data.lead_id, editingRespondLink.id, { contact_role: contactRole });
      }
    } else {
      await linkLeadRespondContact(data.lead_id, {
        respond_contact_id: pickedRespondContactId,
        contact_role: contactRole,
      });
    }
    closeRespondContactDialog();
    void queryClient.invalidateQueries({ queryKey: ['commercial-lead-respond-contacts', data.lead_id] });
  };

  useEffect(() => {
    if (!showCreateRespondContactDialog) return;
    if (newRespondWorkspaceId) return;
    const preferred = leadRespondLinks[0]?.contact.respond_workspace_id || '';
    if (preferred && respondWorkspaceOptions.some((w) => w.id === preferred)) {
      setNewRespondWorkspaceId(String(preferred));
      return;
    }
    const first = respondWorkspaceOptions[0]?.id || '';
    if (first) setNewRespondWorkspaceId(first);
  }, [showCreateRespondContactDialog, newRespondWorkspaceId, respondWorkspaceOptions, leadRespondLinks]);

  const stageNavigation = useMemo(() => {
    if (!data) {
      return {
        nextStage: null as WorkflowStageRow | null,
        prevStage: null as WorkflowStageRow | null,
        current: null as WorkflowStageRow | null,
      };
    }
    const stages = [...projectStages].filter((s) => s.is_active !== false);
    stages.sort((a, b) => a.sort_order - b.sort_order || a.code.localeCompare(b.code));
    const curIdx = stages.findIndex((s) => s.id === data.project_stage_id);
    const nextStage = curIdx >= 0 && curIdx < stages.length - 1 ? stages[curIdx + 1]! : null;
    const current = curIdx >= 0 ? stages[curIdx]! : null;
    const prevStage = current?.can_go_back && curIdx > 0 ? stages[curIdx - 1]! : null;
    return { nextStage, prevStage, current };
  }, [projectStages, data]);

  if (isLoading || !data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-full max-w-md" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  return (
    <div className="relative space-y-6">
      <div>
        <Link
          href="/commercial-management/projects"
          className="mb-3 inline-flex items-center gap-1.5 text-sm text-[#4a5565] hover:text-[#101828]"
        >
          <ArrowLeft className="size-4" aria-hidden />
          Back to projects
        </Link>
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-start sm:justify-between sm:gap-x-4">
          <div className="min-w-0 space-y-2">
            <div className="flex flex-wrap items-center gap-2 gap-y-1">
              <h1 className="truncate text-2xl font-semibold leading-8 tracking-tight text-[#101828]">
                {formatProjectDisplayCode(data.id)}
              </h1>
              <Badge
                variant="secondary"
                className={cn(
                  'h-7 shrink-0 px-2.5 text-xs font-medium normal-case',
                  projectStageHeaderBadgeClass(data.project_stage?.code ?? data.project_stage_code ?? data.status),
                )}
              >
                {stageNavigation.current?.label ?? data.project_stage?.label ?? data.status}
              </Badge>
            </div>
            <p className="text-muted-foreground text-xs">Created {formatDateTimeInMalaysia(data.created_at)}</p>
          </div>
          {canEditProject ? (
            <div className="flex shrink-0 items-stretch">
              <Button
                type="button"
                disabled={!stageNavigation.nextStage || updateMut.isPending}
                className="h-11 min-w-[10rem] rounded-e-none rounded-s-md bg-[#e7000b] px-6 text-base font-medium text-white hover:bg-[#e7000b]/90 disabled:opacity-60"
                onClick={() => {
                  const n = stageNavigation.nextStage;
                  if (n) updateMut.mutate({ project_stage_id: n.id });
                }}
              >
                {stageNavigation.nextStage ? stageNavigation.nextStage.label : 'No next stage'}
              </Button>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    type="button"
                    className="h-11 rounded-e-md rounded-s-none border-l border-[#c10007] bg-[#e7000b] px-3 text-white hover:bg-[#e7000b]/90"
                    aria-label="More project actions"
                    disabled={updateMut.isPending}
                  >
                    <ChevronDown className="size-4 opacity-95" aria-hidden />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="min-w-[14rem] rounded-[10px] border border-[#e5e7eb] shadow-lg">
                  <DropdownMenuItem className="gap-2" onClick={() => router.push(`/commercial-management/projects/${projectId}/edit`)}>
                    <Pencil className="size-4 shrink-0" aria-hidden />
                    Edit project
                  </DropdownMenuItem>
                  {canDuplicateProject ? (
                    <DropdownMenuItem
                      className="gap-2"
                      onClick={async () => {
                        try {
                          const dup = await duplicateCommercialProject(projectId);
                          toast.success(`Project ${dup.title} copied successfully`);
                          router.push(`/commercial-management/projects/${dup.id}`);
                        } catch (e) {
                          toast.error(e instanceof Error ? e.message : 'Failed to duplicate project');
                        }
                      }}
                    >
                      <Copy className="size-4 shrink-0" aria-hidden />
                      Duplicate project
                    </DropdownMenuItem>
                  ) : null}
                  {canShareOwnership ? (
                    <DropdownMenuItem
                      className="gap-2"
                      onClick={async () => {
                        try {
                          if (amOwner) {
                            await disownProject(projectId);
                            toast.success('You are no longer an owner for this project');
                          } else {
                            await shareProjectOwnership(projectId);
                            toast.success('You are now an owner for this project');
                          }
                          void queryClient.invalidateQueries({ queryKey: ['commercial-project', projectId] });
                        } catch (e) {
                          toast.error(e instanceof Error ? e.message : 'Failed to update ownership');
                        }
                      }}
                    >
                      <UserPlus className="size-4 shrink-0" aria-hidden />
                      {amOwner ? 'Disown' : 'Own'}
                    </DropdownMenuItem>
                  ) : null}
                  <DropdownMenuItem className="gap-2 text-[#e7000b] focus:text-[#e7000b]" onClick={() => setDeleteOpen(true)}>
                    <Trash2 className="size-4 shrink-0" aria-hidden />
                    Delete project
                  </DropdownMenuItem>
                  {stageNavigation.prevStage ? (
                    <DropdownMenuItem
                      className="gap-2"
                      disabled={updateMut.isPending}
                      onClick={() => {
                        const p = stageNavigation.prevStage;
                        if (p) updateMut.mutate({ project_stage_id: p.id });
                      }}
                    >
                      <Undo2 className="size-4 shrink-0" aria-hidden />
                      Previous: {stageNavigation.prevStage.label}
                    </DropdownMenuItem>
                  ) : null}
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          ) : canDuplicateProject || canShareOwnership ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button type="button" className="h-11 rounded-md bg-[#e7000b] px-4 text-base font-medium text-white hover:bg-[#e7000b]/90">
                  Actions
                  <ChevronDown className="ms-2 inline size-4 opacity-95" aria-hidden />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="min-w-[14rem] rounded-[10px] border border-[#e5e7eb] shadow-lg">
                {canDuplicateProject ? (
                  <DropdownMenuItem
                    className="gap-2"
                    onClick={async () => {
                      try {
                        const dup = await duplicateCommercialProject(projectId);
                        toast.success(`Project ${dup.title} copied successfully`);
                        router.push(`/commercial-management/projects/${dup.id}`);
                      } catch (e) {
                        toast.error(e instanceof Error ? e.message : 'Failed to duplicate project');
                      }
                    }}
                  >
                    <Copy className="size-4 shrink-0" aria-hidden />
                    Duplicate project
                  </DropdownMenuItem>
                ) : null}
                {canShareOwnership ? (
                  <DropdownMenuItem
                    className="gap-2"
                    onClick={async () => {
                      try {
                        if (amOwner) {
                          await disownProject(projectId);
                          toast.success('You are no longer an owner for this project');
                        } else {
                          await shareProjectOwnership(projectId);
                          toast.success('You are now an owner for this project');
                        }
                        void queryClient.invalidateQueries({ queryKey: ['commercial-project', projectId] });
                      } catch (e) {
                        toast.error(e instanceof Error ? e.message : 'Failed to update ownership');
                      }
                    }}
                  >
                    <UserPlus className="size-4 shrink-0" aria-hidden />
                    {amOwner ? 'Disown' : 'Own'}
                  </DropdownMenuItem>
                ) : null}
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null}
        </div>
      </div>

      <Tabs value={mainTab} onValueChange={setMainTab} className="space-y-6">
        <div className="border-b border-[#e5e7eb] bg-white">
          <TabsList className="flex h-auto w-full flex-wrap gap-0 rounded-none border-0 bg-transparent p-0 px-6 shadow-none">
            <TabsTrigger
              value="overview"
              className={cn(
                'relative rounded-none border-0 border-b-2 border-transparent bg-transparent px-1 py-3 text-sm font-medium text-[#4a5565] shadow-none',
                'cursor-pointer hover:text-[#0a0a0a]',
                'mr-8 data-[state=active]:border-[#e7000b] data-[state=active]:bg-transparent data-[state=active]:text-[#e7000b] data-[state=active]:shadow-none',
              )}
            >
              Overview
            </TabsTrigger>
            <TabsTrigger
              value="tasks"
              className={cn(
                'relative rounded-none border-0 border-b-2 border-transparent bg-transparent px-1 py-3 text-sm font-medium text-[#4a5565] shadow-none',
                'cursor-pointer hover:text-[#0a0a0a]',
                'mr-8 data-[state=active]:border-[#e7000b] data-[state=active]:bg-transparent data-[state=active]:text-[#e7000b] data-[state=active]:shadow-none',
              )}
            >
              Tasks ({projectTabCounts.tasks})
            </TabsTrigger>
            {canViewQuotations ? (
              <TabsTrigger
                value="quotations"
                className={cn(
                  'relative rounded-none border-0 border-b-2 border-transparent bg-transparent px-1 py-3 text-sm font-medium text-[#4a5565] shadow-none',
                  'cursor-pointer hover:text-[#0a0a0a]',
                  'mr-8 data-[state=active]:border-[#e7000b] data-[state=active]:bg-transparent data-[state=active]:text-[#e7000b] data-[state=active]:shadow-none',
                )}
              >
                Quotations ({projectTabCounts.quotations})
              </TabsTrigger>
            ) : null}
            {canViewQuotations ? (
              <TabsTrigger
                value="sales-orders"
                className={cn(
                  'relative rounded-none border-0 border-b-2 border-transparent bg-transparent px-1 py-3 text-sm font-medium text-[#4a5565] shadow-none',
                  'cursor-pointer hover:text-[#0a0a0a]',
                  'mr-8 data-[state=active]:border-[#e7000b] data-[state=active]:bg-transparent data-[state=active]:text-[#e7000b] data-[state=active]:shadow-none',
                )}
              >
                Sales Orders ({projectTabCounts.salesOrders})
              </TabsTrigger>
            ) : null}
            <TabsTrigger
              value="billing"
              className={cn(
                'relative rounded-none border-0 border-b-2 border-transparent bg-transparent px-1 py-3 text-sm font-medium text-[#4a5565] shadow-none',
                'cursor-pointer hover:text-[#0a0a0a]',
                'mr-8 data-[state=active]:border-[#e7000b] data-[state=active]:bg-transparent data-[state=active]:text-[#e7000b] data-[state=active]:shadow-none',
              )}
            >
              Billing ({projectTabCounts.billing})
            </TabsTrigger>
            <TabsTrigger
              value="documents"
              className={cn(
                'relative rounded-none border-0 border-b-2 border-transparent bg-transparent px-1 py-3 text-sm font-medium text-[#4a5565] shadow-none',
                'cursor-pointer hover:text-[#0a0a0a]',
                'mr-8 data-[state=active]:border-[#e7000b] data-[state=active]:bg-transparent data-[state=active]:text-[#e7000b] data-[state=active]:shadow-none',
              )}
            >
              Documents ({projectTabCounts.documents})
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="overview" className="w-full space-y-6 px-6 py-6">
          <div className="grid gap-6 xl:grid-cols-2 xl:items-start">
            <div className="space-y-6">
              <Card className="overflow-hidden rounded-[10px] border border-[#e5e7eb] shadow-none">
                <CardHeader className="flex flex-row items-start justify-between space-y-0 px-6 pb-2 pt-6">
                  <CardTitle className="text-lg font-semibold tracking-tight text-[#0a0a0a]">Project details</CardTitle>
                </CardHeader>
                <CardContent className="grid gap-4 px-6 pb-6">
                  <div className="flex flex-col gap-2">
                    <Label className="text-sm font-medium text-[#4a5565]">Project title</Label>
                    <Textarea
                      readOnly
                      value={data.title?.trim() ? data.title : '—'}
                      rows={3}
                      className="min-h-[88px] resize-y rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground shadow-xs"
                    />
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="flex flex-col gap-2">
                      <Label className="text-sm font-medium text-[#4a5565]">Start date</Label>
                      <div className="flex min-h-10 items-center rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground shadow-xs">
                        {formatDisplayDate(data.start_date)}
                      </div>
                    </div>
                    <div className="flex flex-col gap-2">
                      <Label className="text-sm font-medium text-[#4a5565]">End date</Label>
                      <div className="flex min-h-10 items-center rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground shadow-xs">
                        {formatDisplayDate(data.end_date)}
                      </div>
                    </div>
                  </div>
                  <div className="flex flex-col gap-2">
                    <Label className="text-sm font-medium text-[#4a5565]">Owners</Label>
                    <div className="flex min-h-10 flex-wrap items-center gap-2 rounded-md border border-input bg-background px-3 py-2 text-sm font-medium text-foreground shadow-xs">
                      {(data.owner_names?.length ? data.owner_names : [data.owner_name]).filter(Boolean).map((ownerName, idx) => (
                        <Badge key={`${ownerName}-${idx}`} variant="secondary" className="rounded-full px-2.5 py-1">
                          {ownerName}
                        </Badge>
                      ))}
                    </div>
                  </div>
                  <div className="flex flex-col gap-2">
                    <Label className="text-sm font-medium text-[#4a5565]">Developer</Label>
                    <div className="flex min-h-10 items-center rounded-md border border-input bg-background px-3 py-2 text-sm font-medium text-foreground shadow-xs">
                      {data.developer_customer_name || '—'}
                    </div>
                  </div>
                  <div className="flex flex-col gap-2">
                    <Label className="text-sm font-medium text-[#4a5565]">Brief</Label>
                    <div className="min-h-[88px] whitespace-pre-wrap rounded-md border border-input bg-background px-3 py-2 text-sm text-[#364153] shadow-xs">
                      {data.brief?.trim() ? data.brief : '—'}
                    </div>
                  </div>
                  <div className="flex flex-col gap-2">
                    <Label className="text-sm font-medium text-[#4a5565]">Notes</Label>
                    <div className="min-h-[88px] whitespace-pre-wrap rounded-md border border-input bg-background px-3 py-2 text-sm text-[#364153] shadow-xs">
                      {data.notes?.trim() ? data.notes : '—'}
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card className="overflow-hidden rounded-[10px] border border-[#e5e7eb] shadow-none">
                <CardHeader className="px-6 pb-2 pt-6">
                  <CardTitle className="text-lg font-semibold tracking-tight text-[#0a0a0a]">Lead &amp; sales</CardTitle>
                </CardHeader>
                <CardContent className="grid gap-4 px-6 pb-6">
                  <div className="overflow-x-auto rounded-md border border-input bg-background shadow-xs">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Lead No.</TableHead>
                          <TableHead>Lead Name</TableHead>
                          <TableHead>Client</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {(data.project_leads?.length ? data.project_leads : [
                          {
                            id: data.lead_id,
                            lead_code: data.lead_code,
                            lead_title: data.lead_title,
                            customer_id: data.customer_id,
                            customer_name: data.customer_name,
                          },
                        ]).map((lead) => (
                          <TableRow key={`${lead.id}:${lead.customer_id || 'na'}`}>
                            <TableCell>
                              <Link href={`/commercial/leads/${lead.id}`} className="font-medium text-[#e7000b] hover:underline">
                                {lead.lead_code || lead.id}
                              </Link>
                            </TableCell>
                            <TableCell>{lead.lead_title || '—'}</TableCell>
                            <TableCell>
                              {lead.customer_id ? (
                                <Link
                                  href={`/order-management/customers/${lead.customer_id}`}
                                  className="font-medium text-[#e7000b] hover:underline"
                                >
                                  {lead.customer_name || lead.customer_id}
                                </Link>
                              ) : (
                                '—'
                              )}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                  <div className="flex flex-col gap-2">
                    <Label className="text-sm font-medium text-[#4a5565]">Property / site</Label>
                    <div className="min-h-[72px] whitespace-pre-wrap rounded-md border border-input bg-background px-3 py-2 text-sm text-[#364153] shadow-xs">
                      {propertyAddressLine || '—'}
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>

            <div className="space-y-6">
              <Card className="overflow-hidden rounded-[10px] border border-[#e5e7eb] shadow-none">
                <CardHeader className="px-6 pb-2 pt-6">
                  <CardTitle className="text-lg font-semibold tracking-tight text-[#0a0a0a]">Financial summary</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4 px-6 pb-6 text-sm">
                  <div>
                    <div className="mb-1 text-xs font-medium uppercase tracking-wide text-[#6a7282]">
                      Open quotation amount
                    </div>
                    <div className="font-medium text-[#101828]">
                      {formatAmountByCurrency(data.open_quotation_amount_by_currency ?? {})}
                    </div>
                  </div>
                  <div>
                    <div className="mb-1 text-xs font-medium uppercase tracking-wide text-[#6a7282]">
                      Sales order amount
                    </div>
                    <div className="font-medium text-[#101828]">
                      {formatAmountByCurrency(data.sales_order_amount_by_currency ?? {})}
                    </div>
                  </div>
                  <p className="border-t border-[#e5e7eb] pt-3 text-xs text-[#6a7282]">
                    Updated {formatDateTimeInMalaysia(data.updated_at)}
                  </p>
                </CardContent>
              </Card>

              <Card className="overflow-hidden rounded-[10px] border border-[#e5e7eb] shadow-none">
                <CardHeader className="flex flex-row items-start justify-between space-y-0 px-6 pb-2 pt-6">
                  <div>
                    <CardTitle className="text-lg font-semibold tracking-tight text-[#0a0a0a]">Project members</CardTitle>
                  </div>
                  {canEditProject ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-auto gap-1 p-0 text-sm font-medium text-[#e7000b] hover:bg-transparent hover:text-[#e7000b]/90"
                      onClick={() => {
                        setPendingMemberName('');
                        setMemberDialogOpen(true);
                      }}
                    >
                      <Plus className="size-4" />
                      Add
                    </Button>
                  ) : null}
                </CardHeader>
                <CardContent className="space-y-3 px-6 pb-6">
                  <div className="space-y-4">
                    {memberRows.map((row, idx) => {
                      return (
                      <div
                        key={`${row.name}-${idx}`}
                        className="flex items-start gap-3 border-b border-[#e5e7eb] pb-4 last:border-0 last:pb-0"
                      >
                        <div
                          className="flex size-10 shrink-0 items-center justify-center rounded-full bg-[#f3f4f6] text-xs font-semibold text-[#364153]"
                          aria-hidden
                        >
                          {initialsFromName(row.name)}
                        </div>
                        <div className="min-w-0 flex-1 space-y-2">
                          <div className="grid gap-2 md:grid-cols-[minmax(170px,280px)_1fr] md:items-start">
                            <div>
                              <Label className="text-xs font-medium uppercase tracking-wide text-[#6a7282]">Name</Label>
                              <Input
                                className="mt-1 border-input bg-background shadow-xs"
                                value={row.name}
                                disabled={!canEditProject}
                                onChange={(e) => {
                                  const nextRows = memberRows.map((r, i) => (i === idx ? { ...r, name: e.target.value } : r));
                                  persistProjectMembers(nextRows);
                                }}
                              />
                            </div>
                            <div>
                              <Label className="text-xs font-medium uppercase tracking-wide text-[#6a7282]">Tags</Label>
                              <div className="mt-1">
                                <div className="flex flex-wrap items-center gap-2">
                                  {row.tags.map((role, ri) => (
                                    <span
                                      key={`${idx}-${ri}-${role}`}
                                      className={cn(
                                        'inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-3 py-1 text-xs font-semibold',
                                        ri % 2 === 0
                                          ? 'border-[#c7d2fe] bg-[#eef2ff] text-[#3730a3]'
                                          : 'border-[#e9d5ff] bg-[#f5f3ff] text-[#6b21a8]',
                                      )}
                                    >
                                      <Tag className="size-3.5" />
                                      {role}
                                      {canEditProject ? (
                                        <button
                                          type="button"
                                          className="rounded p-0.5 text-[#6a7282] hover:bg-[#f3f4f6] hover:text-[#101828]"
                                          aria-label={`Remove role ${role}`}
                                          onClick={() => {
                                            const nextRows = memberRows.map((r, i) =>
                                              i === idx ? { ...r, tags: r.tags.filter((x) => x !== role) } : r,
                                            );
                                            persistProjectMembers(nextRows);
                                          }}
                                        >
                                          <X className="size-3" />
                                        </button>
                                      ) : null}
                                    </span>
                                  ))}
                                  {canEditProject ? (
                                    <Input
                                      className="h-8 w-[160px] border-dashed border-[#9ca3af] bg-background text-xs shadow-none"
                                      placeholder="Type role..."
                                      value={memberRoleDraft[idx] ?? ''}
                                      onChange={(e) =>
                                        setMemberRoleDraft((d) => ({
                                          ...d,
                                          [idx]: e.target.value,
                                        }))
                                      }
                                      onKeyDown={(e) => {
                                        if (e.key !== 'Enter') return;
                                        e.preventDefault();
                                        const role = (memberRoleDraft[idx] ?? '').trim();
                                        if (!role) return;
                                        const nextRows = memberRows.map((r, i) =>
                                          i === idx && !r.tags.includes(role)
                                            ? { ...r, tags: [...r.tags, role] }
                                            : r,
                                        );
                                        persistProjectMembers(nextRows);
                                        setMemberRoleDraft((d) => ({ ...d, [idx]: '' }));
                                      }}
                                    />
                                  ) : null}
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>
                        {canEditProject ? (
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="mt-6 shrink-0 self-start"
                            aria-label="Remove member"
                            onClick={() => {
                              const nextRows = memberRows.filter((_, i) => i !== idx);
                              persistProjectMembers(nextRows);
                            }}
                          >
                            <X className="size-4" />
                          </Button>
                        ) : null}
                      </div>
                    );
                    })}
                  </div>
                </CardContent>
              </Card>

              <Card className="overflow-hidden rounded-[10px] border border-[#e5e7eb] shadow-none">
                <CardHeader className="flex flex-row items-center justify-between gap-3 border-b border-[#e5e7eb] px-6 py-4">
                  <CardTitle className="text-lg font-semibold tracking-tight text-[#0a0a0a]">Customer contacts</CardTitle>
                  {canEditProject ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-auto gap-1 p-0 text-sm font-medium text-[#e7000b] hover:bg-transparent hover:text-[#e7000b]/90"
                      onClick={() => setRespondContactDialogOpen(true)}
                    >
                      <Plus className="size-4" />
                      Add
                    </Button>
                  ) : null}
                </CardHeader>
                <CardContent className="space-y-2 px-6 pb-6 pt-4">
                  {!leadRespondLinks.length ? (
                    <p className="text-muted-foreground text-sm">No contacts linked to this lead yet.</p>
                  ) : (
                    <Sortable
                      value={leadRespondLinks}
                      onValueChange={() => {}}
                      getItemValue={(row) => row.id}
                      onMove={({ activeIndex, overIndex }) => {
                        const next = [...leadRespondLinks];
                        const [moved] = next.splice(activeIndex, 1);
                        next.splice(overIndex, 0, moved);
                        void saveLeadRespondContactOrder(next)
                          .then(() => {
                            void queryClient.invalidateQueries({ queryKey: ['commercial-lead-respond-contacts', data.lead_id] });
                          })
                          .catch((e) => toast.error(e instanceof Error ? e.message : 'Failed to reorder contacts'));
                      }}
                      className="space-y-3"
                    >
                      {leadRespondLinks.map((row) => (
                        <SortableItem
                          key={row.id}
                          value={row.id}
                          className="flex flex-wrap items-start gap-3 rounded-lg border border-[#e5e7eb] bg-white px-4 py-3"
                        >
                          <SortableItemHandle className="mt-1 flex size-8 items-center justify-center text-[#9ca3af]">
                            <GripVertical className="size-4" />
                          </SortableItemHandle>
                          <UserRound className="text-muted-foreground mt-0.5 size-9 shrink-0 rounded-full border border-[#e5e7eb] bg-[#f9fafb] p-2" aria-hidden />
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="font-semibold text-[#0a0a0a]">{contactLabel(row)}</span>
                              {row.contact_role === 'main' ? (
                                <span className="rounded px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-[#e7000b]">
                                  Main
                                </span>
                              ) : null}
                            </div>
                          </div>
                          {canEditProject ? (
                            <div className="flex shrink-0 items-center gap-1">
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                className={cn(
                                  'size-9',
                                  row.contact_role === 'main' ? 'text-[#e7000b] hover:text-[#e7000b]' : 'text-muted-foreground',
                                )}
                                aria-label={row.contact_role === 'main' ? 'Main contact' : 'Mark as main contact'}
                                onClick={() => void markLeadRespondContactMain(row)}
                              >
                                <Star className={cn('size-4', row.contact_role === 'main' && 'fill-current')} />
                              </Button>
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                className="size-9 text-muted-foreground"
                                aria-label="Edit contact link"
                                onClick={() => {
                                  setEditingRespondLink(row);
                                  setPickedRespondContactId(row.respond_contact_id);
                                  setPickedRespondContactLabel(contactLabel(row));
                                  setMarkAsMainRespondContact(row.contact_role === 'main');
                                  setRespondContactDialogOpen(true);
                                }}
                              >
                                Edit
                              </Button>
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                className="size-9 text-[#e7000b] hover:text-[#e7000b]"
                                aria-label="Remove contact link"
                                onClick={async () => {
                                  await deleteLeadRespondContactLink(data.lead_id!, row.id);
                                  void queryClient.invalidateQueries({ queryKey: ['commercial-lead-respond-contacts', data.lead_id] });
                                }}
                              >
                                <Trash2 className="size-4" />
                              </Button>
                            </div>
                          ) : null}
                        </SortableItem>
                      ))}
                    </Sortable>
                  )}
                </CardContent>
              </Card>
            </div>
          </div>
        </TabsContent>

                <TabsContent value="tasks" className="w-full space-y-4 px-6 py-6">
          <CommercialEntityTaskBoard
            storageKey={`commercial-project-${projectId}`}
            taskBoard={taskBoard}
            onPersist={persistTaskBoard}
            canEdit={canEditProject}
            tasksGroupLabel="Project tasks"
            activitiesParent={{ variant: 'project', parentId: projectId }}
            scheduleBaselineStartDate={data.start_date || null}
            onPreviewSchedule={(body) => previewProjectTaskBoardSchedule(projectId, body)}
            onApplySchedule={(body) => applyProjectTaskBoardSchedule(projectId, body)}
          />
        </TabsContent>

<TabsContent value="quotations" className="w-full space-y-4 px-6 py-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex min-w-0 flex-1 flex-wrap items-center gap-3">
              <p className="text-[#6a7282] text-sm">Quotations for this project.</p>
              {canViewQuotations && !quotationsPending && projectQuotations.length > 0 ? (
                <ListBoardViewToggle
                  value={projectQuotationsViewMode}
                  onChange={setProjectQuotationsViewMode}
                />
              ) : null}
            </div>
            {canAddQuotations ? (
              <Button
                type="button"
                size="sm"
                className="h-10 rounded-[10px] bg-[#e7000b] px-4 text-base font-medium hover:bg-[#e7000b]/90"
                disabled={!data}
                onClick={() => setCreateQuotationOpen(true)}
              >
                <Plus className="size-4" />
                New quotation
              </Button>
            ) : null}
          </div>
          {!canViewQuotations ? (
            <p className="text-muted-foreground text-sm">You don&apos;t have permission to view quotations.</p>
          ) : quotationsPending ? (
            <Card className="overflow-hidden rounded-[10px] border border-[#e5e7eb]">
              <CardContent className="py-10">
                <Skeleton className="mx-auto h-8 w-3/4 max-w-md" />
              </CardContent>
            </Card>
          ) : activeProjectQuotations.length === 0 ? (
            <Card className="overflow-hidden rounded-[10px] border border-[#e5e7eb] bg-white">
              <CardContent className="py-16 text-center">
                <p className="text-muted-foreground text-sm">No quotations yet.</p>
              </CardContent>
            </Card>
          ) : projectQuotationsViewHydrated && projectQuotationsViewMode === 'board' ? (
            <Card className="overflow-hidden rounded-[10px] border border-[#e5e7eb] bg-white p-4 shadow-none">
              <ProjectQuotationsKanban
                quotations={activeProjectQuotations}
                workspaceHref={quotationWorkspaceHref}
                onMoved={() => void refetchProjectQuotations()}
              />
            </Card>
          ) : (
            <Card className="overflow-hidden rounded-[10px] border border-[#e5e7eb] bg-white shadow-none">
              <CardContent className="p-0">
                <ScrollArea className="min-h-[8rem] w-full">
                  <Table>
                    <TableHeader>
                      <TableRow className="border-0 hover:bg-transparent">
                        <TableHead className={Q_TH}>Quotation</TableHead>
                        <TableHead className={Q_TH}>Status</TableHead>
                        <TableHead className={Q_TH}>Lead</TableHead>
                        <TableHead className={Q_TH}>Client</TableHead>
                        <TableHead className={cn(Q_TH, 'text-end')}>Amount</TableHead>
                        <TableHead className={Q_TH}>Owner</TableHead>
                        <TableHead className={Q_TH}>Created</TableHead>
                        <TableHead className={cn(Q_TH, 'w-[88px] text-end')}> </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {activeProjectQuotations.map((q) => {
                        const href = quotationWorkspaceHref(q);
                        return (
                          <TableRow
                            key={q.id}
                            className="h-12 cursor-pointer border-b border-[#e5e7eb] last:border-0 hover:bg-muted/40"
                            onClick={() => router.push(href)}
                          >
                            <TableCell className="max-w-[220px] align-middle">
                              <Link
                                href={href}
                                className={Q_LINK}
                                onClick={(e) => e.stopPropagation()}
                              >
                                {masterQuotationDisplayCode(q)}
                              </Link>
                              {q.title ? <div className="text-muted-foreground truncate text-xs">{q.title}</div> : null}
                            </TableCell>
                            <TableCell className="align-middle">
                              {q.quotation_stage ? (
                                <span
                                  className={cn(
                                    'inline-flex max-w-full truncate rounded px-2 py-1 text-xs font-medium',
                                    quotationStageBadgeClass(q.quotation_stage.stage_code),
                                  )}
                                >
                                  {q.quotation_stage.stage_name}
                                </span>
                              ) : (
                                '—'
                              )}
                            </TableCell>
                            <TableCell className="align-middle">
                              {q.lead_id ? (
                                <Link
                                  href={`/commercial/leads/${encodeURIComponent(q.lead_id)}`}
                                  className={Q_LINK}
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  {q.lead_code?.trim() || q.lead_id}
                                </Link>
                              ) : (
                                '—'
                              )}
                            </TableCell>
                            <TableCell className="align-middle text-sm text-[#101828]">
                              {q.customer_id ? (
                                <Link
                                  href={`/order-management/customers/${encodeURIComponent(q.customer_id)}`}
                                  className={Q_LINK}
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  {(q.customer_name || '').trim() || q.customer_id}
                                </Link>
                              ) : (
                                (q.customer_name || '').trim() || '—'
                              )}
                            </TableCell>
                            <TableCell className="align-middle text-end text-sm tabular-nums text-[#101828]">
                              {!q.quoted_amount ? (
                                '—'
                              ) : (
                                <>
                                  {q.quoted_amount}
                                  {q.quoted_currency ? ` ${q.quoted_currency}` : ''}
                                </>
                              )}
                            </TableCell>
                            <TableCell className="align-middle text-sm">{q.owner_name?.trim() || '—'}</TableCell>
                            <TableCell className="align-middle text-sm tabular-nums text-[#101828]">
                              {formatQuotationListDate(q.created_at)}
                            </TableCell>
                            <TableCell className="text-end align-middle" onClick={(e) => e.stopPropagation()}>
                              <DropdownMenu>
                                <DropdownMenuTrigger asChild>
                                  <Button type="button" variant="ghost" size="icon" className="size-8">
                                    <MoreVertical className="size-4" aria-hidden />
                                  </Button>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent align="end">
                                  {canAddQuotations ? (
                                    <DropdownMenuItem
                                      className="gap-2"
                                      onClick={async (e) => {
                                        e.preventDefault();
                                        try {
                                          const dup = await duplicateMasterQuotation(q.id);
                                          const label = masterQuotationDisplayCode({
                                            quotation_code: dup.quotation_code,
                                            current_working_revision_number: 1,
                                          });
                                          toast.success(`Quotation ${label} copied successfully`);
                                          const dest = `/commercial-management/quotation-revisions?tender=${encodeURIComponent(dup.tender_code)}&quotation=${encodeURIComponent(dup.quotation_code)}&project=${encodeURIComponent(projectId)}`;
                                          router.push(dest);
                                        } catch (err) {
                                          toast.error(err instanceof Error ? err.message : 'Failed to duplicate quotation');
                                        }
                                      }}
                                    >
                                      <Copy className="size-4 shrink-0" aria-hidden />
                                      Duplicate
                                    </DropdownMenuItem>
                                  ) : null}
                                  <DropdownMenuItem className="gap-2" asChild>
                                    <Link href={href}>Open</Link>
                                  </DropdownMenuItem>
                                </DropdownMenuContent>
                              </DropdownMenu>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                  <ScrollBar orientation="horizontal" />
                </ScrollArea>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="sales-orders" className="w-full space-y-4 px-6 py-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <p className="text-[#6a7282] text-sm">Sales orders (converted quotations) for this project.</p>
          </div>
          {!canViewQuotations ? (
            <p className="text-muted-foreground text-sm">You don&apos;t have permission to view quotations.</p>
          ) : quotationsPending ? (
            <Card className="overflow-hidden rounded-[10px] border border-[#e5e7eb]">
              <CardContent className="py-10">
                <Skeleton className="mx-auto h-8 w-3/4 max-w-md" />
              </CardContent>
            </Card>
          ) : projectSalesOrders.length === 0 ? (
            <Card className="overflow-hidden rounded-[10px] border border-[#e5e7eb] bg-white">
              <CardContent className="py-16 text-center">
                <p className="text-muted-foreground text-sm">No sales orders yet.</p>
              </CardContent>
            </Card>
          ) : (
            <Card className="overflow-hidden rounded-[10px] border border-[#e5e7eb] bg-white shadow-none">
              <CardContent className="p-0">
                <ScrollArea className="min-h-[8rem] w-full">
                  <Table>
                    <TableHeader>
                      <TableRow className="border-0 hover:bg-transparent">
                        <TableHead className={Q_TH}>Sales Order</TableHead>
                        <TableHead className={Q_TH}>Lead</TableHead>
                        <TableHead className={Q_TH}>Client</TableHead>
                        <TableHead className={cn(Q_TH, 'text-end')}>Amount</TableHead>
                        <TableHead className={Q_TH}>Owner</TableHead>
                        <TableHead className={Q_TH}>Created</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {projectSalesOrders.map((q) => {
                        const href = quotationWorkspaceHref(q);
                        return (
                          <TableRow
                            key={q.id}
                            className="h-12 cursor-pointer border-b border-[#e5e7eb] last:border-0 hover:bg-muted/40"
                            onClick={() => router.push(href)}
                          >
                            <TableCell className="max-w-[220px] align-middle">
                              <Link
                                href={href}
                                className={Q_LINK}
                                onClick={(e) => e.stopPropagation()}
                              >
                                {q.sales_order_code || q.quotation_code}
                              </Link>
                              {q.sales_order_code ? (
                                <div className="text-xs text-[#6a7282]">Quotation ref: {q.quotation_code}</div>
                              ) : q.title ? (
                                <div className="text-muted-foreground truncate text-xs">{q.title}</div>
                              ) : null}
                            </TableCell>
                            <TableCell className="align-middle">
                              {q.lead_id ? (
                                <Link
                                  href={`/commercial/leads/${encodeURIComponent(q.lead_id)}`}
                                  className={Q_LINK}
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  {q.lead_code?.trim() || q.lead_id}
                                </Link>
                              ) : (
                                '—'
                              )}
                            </TableCell>
                            <TableCell className="align-middle text-sm text-[#101828]">
                              {q.customer_id ? (
                                <Link
                                  href={`/order-management/customers/${encodeURIComponent(q.customer_id)}`}
                                  className={Q_LINK}
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  {(q.customer_name || '').trim() || q.customer_id}
                                </Link>
                              ) : (
                                (q.customer_name || '').trim() || '—'
                              )}
                            </TableCell>
                            <TableCell className="align-middle text-end text-sm tabular-nums text-[#101828]">
                              {!q.quoted_amount ? (
                                '—'
                              ) : (
                                <>
                                  {q.quoted_amount}
                                  {q.quoted_currency ? ` ${q.quoted_currency}` : ''}
                                </>
                              )}
                            </TableCell>
                            <TableCell className="align-middle text-sm">{q.owner_name?.trim() || '—'}</TableCell>
                            <TableCell className="align-middle text-sm tabular-nums text-[#101828]">
                              {formatQuotationListDate(q.created_at)}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                  <ScrollBar orientation="horizontal" />
                </ScrollArea>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="billing" className="w-full space-y-4 px-6 py-6">
          <Card>
            <CardHeader>
              <CardTitle>Billing</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-muted-foreground text-sm">
                Project billing and invoicing will be connected here. For now, use order and commercial workflows
                elsewhere in the app.
              </p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="documents" className="w-full space-y-4 px-6 py-6">
          <Card>
            <CardHeader>
              <CardTitle>Documents</CardTitle>
            </CardHeader>
            <CardContent>
              {!data.documents?.length ? (
                <p className="text-muted-foreground text-sm">No documents linked to this project.</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Name</TableHead>
                      <TableHead>Uploaded</TableHead>
                      <TableHead className="text-end">Size</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.documents.map((d) => (
                      <TableRow key={d.id}>
                        <TableCell>
                          <a
                            href={d.file_path}
                            className="text-primary hover:underline"
                            target="_blank"
                            rel="noreferrer"
                          >
                            {d.name}
                          </a>
                        </TableCell>
                        <TableCell>{formatDateTimeInMalaysia(d.uploaded_at)}</TableCell>
                        <TableCell className="text-end">
                          {d.size_bytes != null ? `${d.size_bytes}` : '—'}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <CreateQuotationDialog
        open={createQuotationOpen}
        onOpenChange={setCreateQuotationOpen}
        preset={
          data
            ? {
                projectId,
                customerId: data.customer_id,
                clientLabel: (data.customer_name || '—').trim() || '—',
                projectLabel: (data.title || '—').trim() || '—',
                defaultTitle: data.title ? `${data.title} quotation` : 'New quotation',
              }
            : null
        }
        onCreated={() => {
          void refetchProjectQuotations();
          void queryClient.invalidateQueries({ queryKey: ['commercial-project', projectId] });
        }}
      />

      <Dialog open={memberDialogOpen} onOpenChange={setMemberDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Add Project Member</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 py-2">
            <div className="grid gap-2">
              <Label>Name</Label>
              <Input
                value={pendingMemberName}
                onChange={(e) => setPendingMemberName(e.target.value)}
                placeholder="Enter member name"
              />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setMemberDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              onClick={() => {
                const name = pendingMemberName.trim();
                if (!name) return;
                const nextRows = [
                  ...memberRows,
                  {
                    name,
                    tags: [],
                  },
                ];
                persistProjectMembers(nextRows);
                setPendingMemberName('');
                setMemberDialogOpen(false);
              }}
              disabled={!pendingMemberName.trim()}
            >
              Add
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={respondContactDialogOpen}
        onOpenChange={(open) => {
          if (!open) closeRespondContactDialog();
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{editingRespondLink ? 'Edit Respond contact link' : 'Add Respond contact'}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 py-2">
            {!showCreateRespondContactDialog ? (
              <div className="grid gap-2">
                <Label>Search by phone or name</Label>
                <Popover open={respondContactSearchOpen} onOpenChange={setRespondContactSearchOpen}>
                  <PopoverTrigger asChild>
                    <Button variant="outline" type="button" role="combobox" className="w-full justify-between font-normal">
                      <span className={cn('truncate', !pickedRespondContactLabel && 'text-muted-foreground')}>
                        {pickedRespondContactLabel || 'Search existing contact...'}
                      </span>
                      <ChevronDown className="size-4 opacity-70" />
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-(--radix-popper-anchor-width) p-0" align="start">
                    <Command shouldFilter={false}>
                      <CommandInput
                        placeholder="Type at least one character..."
                        value={respondContactSearch}
                        onValueChange={setRespondContactSearch}
                      />
                      <CommandList>
                        <CommandEmpty>
                          <div className="flex flex-col gap-2 py-2">
                            <span className="text-muted-foreground text-sm">
                              {respondContactSearchDebounced.trim().length > 0 ? 'No matches found.' : 'Type at least one character...'}
                            </span>
                            {respondContactSearchDebounced.trim().length > 0 ? (
                              <Button
                                type="button"
                                variant="outline"
                                className="border-[#e7000b] text-[#e7000b] hover:bg-[#fef2f2]"
                                onClick={() => {
                                  setShowCreateRespondContactDialog(true);
                                  setRespondContactSearchOpen(false);
                                  setNewRespondWorkspaceId(String(leadRespondLinks[0]?.contact.respond_workspace_id || ''));
                                  setNewRespondPhone(respondContactSearch.trim());
                                }}
                              >
                                Create new Respond contact
                              </Button>
                            ) : null}
                          </div>
                        </CommandEmpty>
                        <CommandGroup>
                          {respondSearchHits.map((h) => {
                            const optionLabel = searchHitLabel(h);
                            return (
                              <CommandItem
                                key={h.id}
                                value={optionLabel}
                                onSelect={() => {
                                  setPickedRespondContactId(h.id);
                                  setPickedRespondContactLabel(optionLabel);
                                  setRespondContactSearchOpen(false);
                                }}
                              >
                                <span className="truncate">{optionLabel}</span>
                              </CommandItem>
                            );
                          })}
                        </CommandGroup>
                      </CommandList>
                    </Command>
                  </PopoverContent>
                </Popover>
              </div>
            ) : (
              <div className="space-y-3 rounded-md border border-[#e5e7eb] p-3">
                <div className="flex items-center justify-between">
                  <Label>Create new Respond contact</Label>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-auto p-0 text-[#4a5565]"
                    onClick={() => {
                      setShowCreateRespondContactDialog(false);
                      setNewRespondWorkspaceId('');
                      setNewRespondPhone('');
                      setNewRespondName('');
                      setNewRespondUserType('');
                    }}
                  >
                    Back to search
                  </Button>
                </div>
                <div className="space-y-2">
                  <Label>Respond workspace</Label>
                  <Select
                    value={newRespondWorkspaceId}
                    onValueChange={setNewRespondWorkspaceId}
                    disabled={respondWorkspaceLoading || respondWorkspaceOptions.length === 0}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder={respondWorkspaceLoading ? 'Loading…' : 'Select workspace'} />
                    </SelectTrigger>
                    <SelectContent>
                      {respondWorkspaceOptions.map((w) => (
                        <SelectItem key={w.id} value={w.id}>
                          {(w.name || 'Workspace').trim()} ({w.space_id})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Phone number</Label>
                  <Input value={newRespondPhone} onChange={(e) => setNewRespondPhone(e.target.value)} placeholder="+60123456789" />
                </div>
                <div className="space-y-2">
                  <Label>Name (optional)</Label>
                  <Input value={newRespondName} onChange={(e) => setNewRespondName(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label>User Type</Label>
                  <Input
                    value={newRespondUserType}
                    onChange={(e) => setNewRespondUserType(e.target.value)}
                    placeholder="User type (optional)"
                  />
                </div>
              </div>
            )}
            <Button
              type="button"
              variant="outline"
              className={cn(markAsMainRespondContact && 'border-[#e7000b] text-[#e7000b]')}
              onClick={() => setMarkAsMainRespondContact((v) => !v)}
            >
              Mark as main contact
            </Button>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={closeRespondContactDialog}>
              Cancel
            </Button>
            <Button type="button" onClick={() => void submitRespondContactDialog()} disabled={!pickedRespondContactId}>
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <EntityActivitiesDock variant="project" entityId={projectId} canPost={canEditProject} leadIdForMessages={data.lead_id} />

      <AlertDialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete project?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete this project. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-[#e7000b] text-white hover:bg-[#e7000b]/90"
              onClick={() =>
                deleteMut.mutate(projectId, {
                  onSuccess: () => router.push('/commercial-management/projects'),
                })
              }
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
