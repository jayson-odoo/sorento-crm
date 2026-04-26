'use client';

import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Archive,
  ArrowLeft,
  Ban,
  Copy,
  ChevronDown,
  Check,
  ExternalLink,
  GripVertical,
  Info,
  Pencil,
  Plus,
  Star,
  Trash2,
  Undo2,
  UserRound,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { TruncatedTextCell } from '@/components/common/TruncatedTextCell';
import { Alert, AlertContent, AlertIcon, AlertTitle } from '@/components/ui/alert';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  useAddLeadNote,
  useCommercialLead,
  useConvertCommercialLead,
  useLeadNotes,
  useLeadRelated,
  useUpdateCommercialLead,
} from '../hooks/useCommercialLeads';
import { useLeadStagesList } from '../hooks/useLeadStages';
import { deleteCommercialLead, duplicateCommercialLead } from '../services/leadService';
import {
  deleteLeadRespondContactLink,
  linkLeadRespondContact,
  listRespondWorkspaceSelect,
  listLeadRespondContacts,
  searchRespondContacts,
  updateLeadRespondContactLink,
} from '../services/leadRespondContactsService';
import type { LeadRespondContactRow } from '../types/lead.types';
import { getAuditLogs } from '@/services/auditService';
import { getOrders } from '@/app/(protected)/order-management/orders/services/orderService';
import { formatDate, formatDateSafe } from '@/lib/helpers';
import { useHasPermission } from '@/hooks/usePermissions';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { Sortable, SortableItem, SortableItemHandle } from '@/components/ui/sortable';
import { EntityActivitiesDock } from '@/app/(protected)/commercial-management/shared/components/EntityActivitiesDock';
import { apiFetch } from '@/lib/api';
import { CreateQuotationDialog } from '@/app/(protected)/commercial-management/quotations/components/CreateQuotationDialog';
import CreateProjectDialog from '@/app/(protected)/commercial-management/projects/components/CreateProjectDialog';
import { getCommercialProjectsAllPages } from '@/app/(protected)/commercial-management/projects/services/commercialProjectService';
import { getWorkflowStages } from '@/app/(protected)/commercial-core/process-configuration/services/workflowStageService';

interface LeadDetailProps {
  leadId: string;
}

function qualStr(q: Record<string, unknown> | undefined, key: string): string {
  if (!q) return '—';
  const v = q[key];
  if (v == null || v === '') return '—';
  if (typeof v === 'string' || typeof v === 'number') return String(v);
  if (typeof v === 'object' && v !== null && 'label' in v) return String((v as { label: unknown }).label) || '—';
  return '—';
}

/** Solid pills for hero (Figma). */
function stageHeroBadgeClass(stageCode: string | null | undefined): string {
  const c = (stageCode || '').toLowerCase();
  if (c.includes('won')) return 'bg-emerald-600 text-white';
  if (c.includes('lost') || c.includes('withdraw') || c.includes('no_award')) return 'bg-red-600 text-white';
  if (c.includes('proposal')) return 'bg-violet-600 text-white';
  if (c.includes('new')) return 'bg-[#2b7fff] text-white';
  if (c.includes('qualif')) return 'bg-amber-500 text-white';
  return 'bg-sky-600 text-white';
}

/** Avatar URL from qualification — https, or cookie-auth attachment download path. */
function isRenderableLeadProfileImageUrl(raw: string): boolean {
  const u = raw.trim();
  if (!u || u === '—') return false;
  if (u.startsWith('http://') || u.startsWith('https://')) return true;
  if (u.startsWith('/api/v1/resource-management/attachments/') && u.includes('/download')) return true;
  try {
    const parsed = new URL(u);
    return (
      parsed.pathname.includes('/resource-management/attachments/') && parsed.pathname.includes('/download')
    );
  } catch {
    return false;
  }
}

function buildAddress(q: Record<string, unknown>): string {
  const parts = [
    qualStr(q, 'address_line_1'),
    qualStr(q, 'address_line_2'),
    qualStr(q, 'city'),
    qualStr(q, 'postcode'),
    qualStr(q, 'state'),
    qualStr(q, 'country'),
  ].filter((p) => p !== '—');
  return parts.length ? parts.join('\n') : '—';
}

/** Figma overview field — uppercase label #6a7282 */
function OverviewField({ label, children, clientAccent }: { label: string; children: ReactNode; clientAccent?: boolean }) {
  return (
    <div className="flex flex-col gap-1">
      <p className="text-[#6a7282] text-xs font-normal uppercase leading-4">{label}</p>
      <div
        className={cn(
          'text-base font-normal leading-6 tracking-tight text-[#101828]',
          clientAccent && 'font-medium text-[#e7000b]',
        )}
      >
        {children}
      </div>
    </div>
  );
}

/** Match project list status chips on the lead Projects tab */
function leadProjectRowBadgeClass(status: string | null | undefined): string {
  const c = (status || '').toLowerCase();
  if (c.includes('complet')) return 'bg-emerald-100 text-emerald-800';
  if (c.includes('cancel')) return 'bg-[#ffe2e2] text-[#9f0712]';
  if (c.includes('inactive')) return 'bg-[#ffe2e2] text-[#9f0712]';
  if (c.includes('hold')) return 'bg-amber-100 text-amber-900';
  if (c.includes('plan')) return 'bg-[#dbeafe] text-[#1447e6]';
  if (c.includes('active')) return 'bg-[#dcfce7] text-[#016630]';
  return 'bg-zinc-100 text-zinc-700';
}

function leadDetailInitials(title: string, customerName: string | null | undefined): string {
  const t = title.trim();
  const n = (customerName || '').trim();
  if (n.length >= 2) return n.slice(0, 2).toUpperCase();
  if (t.length >= 2) return t.slice(0, 2).toUpperCase();
  if (n.length === 1) return `${n[0]!}?`.toUpperCase();
  return '—';
}

function formatRespondContactOptionLabel(hit: {
  name?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  phone_number: string;
}): string {
  const displayName = [hit.first_name, hit.last_name].filter(Boolean).join(' ').trim() || hit.name || 'Contact';
  return `${displayName} (${hit.phone_number || '—'})`;
}

export default function LeadDetail({ leadId }: LeadDetailProps) {
  const router = useRouter();
  const qc = useQueryClient();
  const { data: lead, isLoading } = useCommercialLead(leadId);
  const { data: notes = [] } = useLeadNotes(leadId);
  const { data: related, isLoading: relatedLoading } = useLeadRelated(leadId);
  const addNote = useAddLeadNote(leadId);
  const convertLead = useConvertCommercialLead(leadId);
  const updateLead = useUpdateCommercialLead(leadId);
  const { data: leadStages = [] } = useLeadStagesList();

  const stageNavigation = useMemo(() => {
    const ordered = [...leadStages]
      .filter((s) => s.is_active !== false)
      .sort((a, b) => a.sort_order - b.sort_order || a.stage_code.localeCompare(b.stage_code));
    const lostStage = leadStages.find((s) => s.is_cancelled) ?? null;
    const curIdx = ordered.findIndex((s) => s.id === lead?.lead_stage_id);
    const current = curIdx >= 0 ? ordered[curIdx] : null;
    const nextStage = current && curIdx >= 0 && curIdx < ordered.length - 1 ? ordered[curIdx + 1]! : null;
    const prevStage = current?.can_go_back && curIdx > 0 ? ordered[curIdx - 1]! : null;
    return { nextStage, prevStage, lostStage, current };
  }, [leadStages, lead?.lead_stage_id]);

  const [activeTab, setActiveTab] = useState('detail');
  const [quotationHintDismissed, setQuotationHintDismissed] = useState(false);
  const [convertOpen, setConvertOpen] = useState(false);
  const [projectTitle, setProjectTitle] = useState('');
  const [tenderTitle, setTenderTitle] = useState('');
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [respondContactOpen, setRespondContactOpen] = useState(false);
  const [respondContactSearchOpen, setRespondContactSearchOpen] = useState(false);
  const [respondContactSearch, setRespondContactSearch] = useState('');
  const [respondContactSearchDebounced, setRespondContactSearchDebounced] = useState('');
  const [pickedRespondContactId, setPickedRespondContactId] = useState<string | null>(null);
  const [pickedRespondContactLabel, setPickedRespondContactLabel] = useState('');
  const [newRespondWorkspaceId, setNewRespondWorkspaceId] = useState('');
  const [newRespondPhone, setNewRespondPhone] = useState('');
  const [newRespondName, setNewRespondName] = useState('');
  const [newRespondUserType, setNewRespondUserType] = useState('');
  const [showCreateRespondContactDialog, setShowCreateRespondContactDialog] = useState(false);
  const [markAsMain, setMarkAsMain] = useState(false);
  const [editingRespondLink, setEditingRespondLink] = useState<LeadRespondContactRow | null>(null);
  const [respondDeleteOpen, setRespondDeleteOpen] = useState(false);
  const [respondPendingDelete, setRespondPendingDelete] = useState<LeadRespondContactRow | null>(null);
  const [createQuotationOpen, setCreateQuotationOpen] = useState(false);
  const [projectChooserOpen, setProjectChooserOpen] = useState(false);
  const [projectPickerOpen, setProjectPickerOpen] = useState(false);
  const [projectSearch, setProjectSearch] = useState('');
  const [selectedProjectId, setSelectedProjectId] = useState('');
  const [createProjectOpen, setCreateProjectOpen] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setRespondContactSearchDebounced(respondContactSearch), 350);
    return () => clearTimeout(t);
  }, [respondContactSearch]);
  const [noteBody, setNoteBody] = useState('');

  const canEdit = useHasPermission('commercial_core.leads.edit');
  const canDuplicateLead = useHasPermission('commercial_core.leads.add');
  const canDelete = useHasPermission('commercial_core.leads.delete');
  const canAddMq = useHasPermission('commercial_core.master_quotations.add');
  const canAddProject = useHasPermission('commercial_core.projects.add');
  const canManageRespondContacts = useHasPermission('commercial_core.leads.edit');

  const { data: leadRespondLinks = [] } = useQuery({
    queryKey: ['commercial-lead-respond-contacts', leadId],
    queryFn: () => listLeadRespondContacts(leadId),
    enabled: !!leadId,
  });

  const { data: respondSearchHits = [] } = useQuery({
    queryKey: ['respond-contact-search', lead?.respond_workspace_id, respondContactSearchDebounced],
    queryFn: () => searchRespondContacts(lead!.respond_workspace_id!, respondContactSearchDebounced),
    enabled:
      !!respondContactOpen &&
      !showCreateRespondContactDialog &&
      !!lead?.respond_workspace_id,
  });

  const { data: respondWorkspaceOptions = [], isLoading: respondWorkspaceLoading } = useQuery({
    queryKey: ['commercial-respond-workspaces-select'],
    queryFn: listRespondWorkspaceSelect,
    enabled: !!respondContactOpen && showCreateRespondContactDialog,
    staleTime: 60_000,
  });

  const { data: auditPage } = useQuery({
    queryKey: ['audit', 'commercial_lead', leadId],
    queryFn: () => getAuditLogs({ entity_type: 'commercial_lead', entity_id: leadId, page: 1, limit: 50 }),
    enabled: !!leadId,
  });

  const { data: ordersPage } = useQuery({
    queryKey: ['lead-customer-orders', lead?.customer_id],
    queryFn: () =>
      getOrders({
        pageIndex: 0,
        pageSize: 50,
        sorting: [{ id: 'created_at', desc: true }],
        searchQuery: '',
        customer_id: lead!.customer_id!,
      }),
    enabled: !!lead?.customer_id,
  });

  const { data: projectOptions = [], isLoading: projectsLoading } = useQuery({
    queryKey: ['lead-project-selector'],
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
        .map((p) => ({ id: p.id, title: p.title }));
    },
    enabled: projectChooserOpen,
    staleTime: 30_000,
  });

  const { data: projectOptionsByStatusFallback = [], isLoading: projectsFallbackLoading } = useQuery({
    queryKey: ['lead-project-selector-fallback'],
    queryFn: async () => {
      const allProjects = await getCommercialProjectsAllPages({
        searchQuery: '',
        sorting: [],
      });
      return (allProjects.data ?? [])
        .filter((p) => {
          const status = (p.status || '').toLowerCase();
          return status !== 'completed' && status !== 'cancelled';
        })
        .map((p) => ({ id: p.id, title: p.title }));
    },
    enabled: projectChooserOpen && projectOptions.length === 0,
    staleTime: 30_000,
  });

  const designRows = useMemo(() => {
    const q = lead?.qualification || {};
    const raw = q.design_links;
    if (!Array.isArray(raw)) return [] as { name: string; url: string }[];
    return raw
      .map((x: unknown) => {
        if (typeof x !== 'object' || !x || !('url' in x)) return null;
        const o = x as { name?: unknown; url: unknown };
        return { name: String(o.name || 'Design'), url: String(o.url) };
      })
      .filter((x): x is { name: string; url: string } => x != null && !!x.url);
  }, [lead?.qualification]);

  const tabCounts = useMemo(
    () => ({
      quotations: related?.quotations?.length ?? 0,
      salesOrders: related?.sales_orders?.length ?? 0,
      invoices: ordersPage?.data?.length ?? 0,
      projects: related?.projects?.length ?? 0,
    }),
    [
      related?.quotations,
      related?.sales_orders,
      related?.projects,
      ordersPage?.data,
    ],
  );

  const filteredProjectOptions = useMemo(() => {
    const q = projectSearch.trim().toLowerCase();
    const rows = projectOptions.length ? projectOptions : projectOptionsByStatusFallback;
    if (!q) return rows;
    return rows.filter((p) => (p.title || '').toLowerCase().includes(q));
  }, [projectOptions, projectOptionsByStatusFallback, projectSearch]);
  const availableProjectOptions = projectOptions.length ? projectOptions : projectOptionsByStatusFallback;
  const projectsPickerLoading = projectsLoading || projectsFallbackLoading;

  const mergedHistory = useMemo(() => {
    const rows: { at: string; label: string; detail: string }[] = [];
    for (const n of notes) {
      rows.push({
        at: n.created_at,
        label: 'Note',
        detail: `${n.created_by_name || 'User'}: ${n.body}`,
      });
    }
    for (const a of auditPage?.data || []) {
      rows.push({
        at: a.changed_at,
        label: a.action,
        detail: a.description || JSON.stringify(a.new_values || a.old_values || {}),
      });
    }
    rows.sort((x, y) => (x.at < y.at ? 1 : x.at > y.at ? -1 : 0));
    return rows;
  }, [notes, auditPage]);

  const primaryProjectId = related?.projects?.[0]?.id || lead?.project_id || null;

  const closeRespondContactDialog = () => {
    setRespondContactOpen(false);
    setRespondContactSearchOpen(false);
    setRespondContactSearch('');
    setRespondContactSearchDebounced('');
    setPickedRespondContactId(null);
    setPickedRespondContactLabel('');
    setNewRespondWorkspaceId('');
    setNewRespondPhone('');
    setNewRespondName('');
    setNewRespondUserType('');
    setMarkAsMain(false);
    setShowCreateRespondContactDialog(false);
    setEditingRespondLink(null);
  };

  const openRespondContactCreate = () => {
    if (!lead?.respond_workspace_id) {
      toast.error('Choose a Respond workspace on Edit lead before adding contacts.');
      return;
    }
    setEditingRespondLink(null);
    setRespondContactSearchOpen(false);
    setRespondContactSearch('');
    setPickedRespondContactId(null);
    setPickedRespondContactLabel('');
    setNewRespondWorkspaceId(lead.respond_workspace_id || '');
    setNewRespondPhone('');
    setNewRespondName('');
    setNewRespondUserType('');
    setMarkAsMain(false);
    setShowCreateRespondContactDialog(false);
    setRespondContactOpen(true);
  };

  const openRespondLinkEdit = (row: LeadRespondContactRow) => {
    setEditingRespondLink(row);
    setRespondContactSearchOpen(false);
    setPickedRespondContactId(row.respond_contact_id);
    setPickedRespondContactLabel(formatRespondContactOptionLabel(row.contact));
    setNewRespondWorkspaceId(String(row.contact.respond_workspace_id || lead?.respond_workspace_id || ''));
    setMarkAsMain(row.contact_role === 'main');
    setShowCreateRespondContactDialog(false);
    setRespondContactOpen(true);
  };

  const saveRespondContactOrder = async (rows: LeadRespondContactRow[]) => {
    if (!lead?.id) return;
    await Promise.all(
      rows.map((row, index) =>
        updateLeadRespondContactLink(lead.id, row.id, {
          sort_order: index,
        }),
      ),
    );
  };

  const markRespondLinkAsMain = async (row: LeadRespondContactRow) => {
    if (!lead?.id || row.contact_role === 'main') return;
    try {
      await updateLeadRespondContactLink(lead.id, row.id, { contact_role: 'main' });
      toast.success('Main contact updated');
      void qc.invalidateQueries({ queryKey: ['commercial-lead-respond-contacts', leadId] });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to set main contact');
    }
  };

  useEffect(() => {
    if (!showCreateRespondContactDialog) return;
    if (newRespondWorkspaceId) return;
    const preferred = lead?.respond_workspace_id || '';
    if (preferred && respondWorkspaceOptions.some((w) => w.id === preferred)) {
      setNewRespondWorkspaceId(preferred);
      return;
    }
    const first = respondWorkspaceOptions[0]?.id || '';
    if (first) setNewRespondWorkspaceId(first);
  }, [showCreateRespondContactDialog, newRespondWorkspaceId, respondWorkspaceOptions, lead?.respond_workspace_id]);

  const submitRespondContactDialog = async () => {
    if (!lead) return;
    try {
      const role: 'main' | 'stakeholder' = markAsMain ? 'main' : 'stakeholder';

      if (showCreateRespondContactDialog) {
        if (!newRespondWorkspaceId) {
          toast.error('Respond workspace is required');
          return;
        }
        if (!newRespondPhone.trim()) {
          toast.error('Phone is required');
          return;
        }
        const createResponse = await apiFetch('/api/user-management/contacts', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            respond_workspace_id: newRespondWorkspaceId,
            phone_number: newRespondPhone.trim(),
            name: newRespondName.trim() || null,
            user_type: newRespondUserType.trim() || null,
          }),
        });
        if (!createResponse.ok) {
          const err = await createResponse.json().catch(() => ({}));
          throw new Error((err as { detail?: string; message?: string }).detail || (err as { message?: string }).message || 'Failed to create contact');
        }
        const created = (await createResponse.json()) as { id: string; phone_number: string; name?: string | null };
        await linkLeadRespondContact(lead.id, {
          respond_contact_id: created.id,
          contact_role: role,
        });
        if (editingRespondLink && created.id !== editingRespondLink.id) {
          await deleteLeadRespondContactLink(lead.id, editingRespondLink.id);
        }
        setPickedRespondContactId(created.id);
        setPickedRespondContactLabel(
          `${(created.name || newRespondName || 'Contact').trim() || 'Contact'} (${created.phone_number || newRespondPhone.trim()})`,
        );
        toast.success(editingRespondLink ? 'Contact link updated' : 'Contact added');
      } else {
        if (!pickedRespondContactId) {
          toast.error('Select a contact');
          return;
        }
        if (editingRespondLink) {
          if (pickedRespondContactId !== editingRespondLink.respond_contact_id) {
            await linkLeadRespondContact(lead.id, {
              respond_contact_id: pickedRespondContactId,
              contact_role: role,
              sort_order: editingRespondLink.sort_order,
            });
            await deleteLeadRespondContactLink(lead.id, editingRespondLink.id);
            toast.success('Contact link updated');
          } else {
            await updateLeadRespondContactLink(lead.id, editingRespondLink.id, {
              contact_role: role,
            });
            toast.success('Contact link updated');
          }
        } else {
          await linkLeadRespondContact(lead.id, {
            respond_contact_id: pickedRespondContactId,
            contact_role: role,
          });
          toast.success('Contact linked');
        }
      }
      closeRespondContactDialog();
      void qc.invalidateQueries({ queryKey: ['commercial-lead-respond-contacts', leadId] });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to save');
    }
  };

  if (isLoading || !lead) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  const q = lead.qualification || {};
  const profileImageUrl = qualStr(q, 'profile_image_url');
  const showProfileImage = profileImageUrl !== '—' && isRenderableLeadProfileImageUrl(profileImageUrl);
  const showQuotationHint =
    !!lead &&
    lead.has_project &&
    !!primaryProjectId &&
    canAddMq &&
    !quotationHintDismissed;
  const openCreateQuotationFlow = () => {
    setActiveTab('quotations');
    setCreateQuotationOpen(true);
  };
  const openProjectFlow = () => {
    setActiveTab('projects');
    setProjectChooserOpen(true);
    setProjectSearch('');
    setSelectedProjectId('');
  };

  return (
    <div className="space-y-6 pb-10">
      <header className="border-b border-[#e5e7eb] bg-[#f9fafb]">
        <div className="w-full px-6 pt-6">
          <button
            type="button"
            className="flex items-center gap-2 text-sm font-medium text-[#4a5565] transition-colors hover:text-[#0a0a0a]"
            onClick={() => router.push('/commercial/leads')}
          >
            <ArrowLeft className="size-4 shrink-0" aria-hidden />
            Back to leads
          </button>
          <div className="mt-5 flex flex-col gap-6 pb-6 lg:flex-row lg:items-start lg:justify-between">
            <div className="flex min-w-0 gap-4">
              <div className="border-border/60 relative size-20 shrink-0 overflow-hidden rounded-full border bg-[#ffe2e2] shadow-inner">
                {showProfileImage ? (
                  <img src={profileImageUrl} alt="" className="size-full object-cover" />
                ) : (
                  <div className="text-primary flex size-full items-center justify-center text-xl font-semibold tracking-tight">
                    {leadDetailInitials(lead.title, lead.customer_name)}
                  </div>
                )}
              </div>
              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex flex-wrap items-center gap-3">
                  <h1 className="truncate text-[30px] font-semibold leading-9 tracking-tight text-[#0a0a0a]">
                    Lead: {lead.lead_code}
                  </h1>
                  {lead.stage_name || lead.stage_code ? (
                    <span
                      className={cn(
                        'inline-flex shrink-0 items-center rounded px-2 py-1 text-xs font-medium text-white',
                        stageHeroBadgeClass(lead.stage_code),
                      )}
                    >
                      {lead.stage_name || lead.stage_code}
                    </span>
                  ) : null}
                </div>
                <p className="truncate text-sm leading-5 text-[#4a5565]">{lead.title}</p>
              </div>
            </div>
            {canEdit ? (
              <div className="flex shrink-0 items-stretch">
                <Button
                  type="button"
                  disabled={!stageNavigation.nextStage || updateLead.isPending}
                  className="h-11 min-w-[10rem] rounded-e-none rounded-s-[4px] bg-[#e7000b] px-6 text-base font-medium text-white hover:bg-[#e7000b]/90 disabled:opacity-60"
                  onClick={() => {
                    if (stageNavigation.nextStage) {
                      updateLead.mutate({ lead_stage_id: stageNavigation.nextStage.id });
                    }
                  }}
                >
                  {stageNavigation.nextStage ? stageNavigation.nextStage.stage_name : 'No next stage'}
                </Button>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      type="button"
                      className="h-11 rounded-e-[4px] rounded-s-none border-l border-[#c10007] bg-[#e7000b] px-3 text-white hover:bg-[#e7000b]/90"
                      aria-label="More lead actions"
                    >
                      <ChevronDown className="size-4 opacity-95" aria-hidden />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="min-w-[14rem] rounded-[10px] border border-[#e5e7eb] shadow-lg">
                    <DropdownMenuItem
                      className="gap-2"
                      onClick={() => router.push(`/commercial/leads/${lead.id}/edit`)}
                    >
                      <Pencil className="size-4 shrink-0" aria-hidden />
                      Edit lead
                    </DropdownMenuItem>
                    {canDuplicateLead ? (
                      <DropdownMenuItem
                        className="gap-2"
                        onClick={async () => {
                          try {
                            const dup = await duplicateCommercialLead(lead.id);
                            toast.success(`Lead ${dup.lead_code} copied successfully`);
                            router.push(`/commercial/leads/${dup.id}`);
                          } catch (e) {
                            toast.error(e instanceof Error ? e.message : 'Failed to duplicate lead');
                          }
                        }}
                      >
                        <Copy className="size-4 shrink-0" aria-hidden />
                        Duplicate lead
                      </DropdownMenuItem>
                    ) : null}
                    {canAddMq ? (
                      <DropdownMenuItem className="gap-2" onClick={openCreateQuotationFlow}>
                        <Plus className="size-4 shrink-0" aria-hidden />
                        Create quotation
                      </DropdownMenuItem>
                    ) : null}
                    {canDelete ? (
                      <DropdownMenuItem className="gap-2" onClick={() => setDeleteOpen(true)}>
                        <Archive className="size-4 shrink-0" aria-hidden />
                        Archive lead
                      </DropdownMenuItem>
                    ) : null}
                    {stageNavigation.prevStage ? (
                      <DropdownMenuItem
                        className="gap-2"
                        disabled={updateLead.isPending}
                        onClick={() => {
                          const p = stageNavigation.prevStage;
                          if (p) updateLead.mutate({ lead_stage_id: p.id });
                        }}
                      >
                        <Undo2 className="size-4 shrink-0" aria-hidden />
                        Previous: {stageNavigation.prevStage.stage_name}
                      </DropdownMenuItem>
                    ) : null}
                    {stageNavigation.lostStage && stageNavigation.lostStage.id !== lead.lead_stage_id ? (
                      <DropdownMenuItem
                        className="gap-2 text-[#e7000b] focus:text-[#e7000b]"
                        disabled={updateLead.isPending}
                        onClick={() => {
                          const lost = stageNavigation.lostStage;
                          if (lost) updateLead.mutate({ lead_stage_id: lost.id });
                        }}
                      >
                        <Ban className="size-4 shrink-0" aria-hidden />
                        Mark as lost
                      </DropdownMenuItem>
                    ) : null}
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            ) : canDuplicateLead ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    type="button"
                    className="h-11 rounded-[4px] bg-[#e7000b] px-4 text-base font-medium text-white hover:bg-[#e7000b]/90"
                  >
                    Actions
                    <ChevronDown className="ms-2 inline size-4 opacity-95" aria-hidden />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="min-w-[14rem] rounded-[10px] border border-[#e5e7eb] shadow-lg">
                  <DropdownMenuItem
                    className="gap-2"
                    onClick={async () => {
                      try {
                        const dup = await duplicateCommercialLead(lead.id);
                        toast.success(`Lead ${dup.lead_code} copied successfully`);
                        router.push(`/commercial/leads/${dup.id}`);
                      } catch (e) {
                        toast.error(e instanceof Error ? e.message : 'Failed to duplicate lead');
                      }
                    }}
                  >
                    <Copy className="size-4 shrink-0" aria-hidden />
                    Duplicate lead
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : null}
          </div>
        </div>
      </header>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
        <div className="border-b border-[#e5e7eb] bg-white">
          <TabsList className="flex h-auto w-full flex-wrap gap-0 rounded-none border-0 bg-transparent p-0 px-6 shadow-none">
            {(
              [
                ['detail', 'Detail'],
                ['quotations', `Quotations (${tabCounts.quotations})`],
                ['sales_orders', `Sales orders (${tabCounts.salesOrders})`],
                ['invoices', `Invoices (${tabCounts.invoices})`],
                ['projects', `Projects (${tabCounts.projects})`],
              ] as const
            ).map(([v, label]) => (
              <TabsTrigger
                key={v}
                value={v}
                className={cn(
                  'relative rounded-none border-0 border-b-2 border-transparent bg-transparent px-1 py-3 text-sm font-medium text-[#4a5565] shadow-none',
                  'cursor-pointer hover:text-[#0a0a0a]',
                  'mr-8 data-[state=active]:border-[#e7000b] data-[state=active]:bg-transparent data-[state=active]:text-[#e7000b] data-[state=active]:shadow-none',
                )}
              >
                {label}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>

        <TabsContent value="detail" className="w-full space-y-6 px-6 py-6">
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="rounded-[10px] border border-[#e5e7eb] bg-white px-6 pb-6 pt-6 shadow-none">
              <h2 className="mb-4 text-lg font-semibold tracking-tight text-[#0a0a0a]">Lead overview</h2>
              <div className="grid gap-6 sm:grid-cols-2">
                <OverviewField label="Client" clientAccent={!!(lead.customer_name && lead.customer_id)}>
                  {lead.customer_name && lead.customer_id ? (
                    <Link
                      href={`/order-management/customers/${lead.customer_id}`}
                      className="font-medium text-[#e7000b] hover:underline"
                    >
                      {lead.customer_name}
                    </Link>
                  ) : (
                    <span className="font-normal text-[#101828]">—</span>
                  )}
                </OverviewField>
                <OverviewField label="Assigned to">{lead.owner_name || '—'}</OverviewField>
                <OverviewField label="Created by">{lead.created_by_name || lead.owner_name || '—'}</OverviewField>
                <OverviewField label="Created">{formatDate(lead.created_at)}</OverviewField>
                <OverviewField label="Assigned on">
                  {formatDateSafe(q.assigned_at as string | undefined, '—')}
                </OverviewField>
                <OverviewField label="Qualified on">
                  {formatDateSafe(q.qualified_at as string | undefined, '—')}
                </OverviewField>
                {lead.allows_conversion ? (
                  <div className="sm:col-span-2 pt-2">
                    <Button type="button" variant="outline" size="sm" onClick={() => setConvertOpen(true)}>
                      Convert lead
                    </Button>
                  </div>
                ) : null}
              </div>
            </div>

            <div className="rounded-[10px] border border-[#e5e7eb] bg-white px-6 pb-6 pt-6 shadow-none">
              <h2 className="mb-4 text-lg font-semibold tracking-tight text-[#0a0a0a]">Property details</h2>
              <div className="grid gap-6 sm:grid-cols-1">
                <OverviewField label="Location">
                  <span className="font-normal whitespace-pre-line text-[#101828]">{buildAddress(q)}</span>
                </OverviewField>
                <OverviewField label="Property type">{qualStr(q, 'property_type')}</OverviewField>
                <OverviewField label="Property value">{qualStr(q, 'property_value')}</OverviewField>
                <OverviewField label="Budget range">{qualStr(q, 'budget_range')}</OverviewField>
                <OverviewField label="Sales closure confidence">{qualStr(q, 'sales_closure_confidence')}</OverviewField>
                <OverviewField label="Est. project start">{qualStr(q, 'est_project_start_date')}</OverviewField>
                <OverviewField label="Est. project end">{qualStr(q, 'est_project_end_date')}</OverviewField>
              </div>
            </div>
          </div>

          <div className="rounded-[10px] border border-[#e5e7eb] bg-white shadow-none">
            <div className="flex flex-row items-center justify-between gap-3 border-b border-[#e5e7eb] px-6 py-4">
              <h2 className="text-lg font-semibold tracking-tight text-[#0a0a0a]">
                Contacts ({leadRespondLinks.length})
              </h2>
              {canManageRespondContacts ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-auto gap-1 p-0 text-sm font-medium text-[#e7000b] hover:bg-transparent hover:text-[#e7000b]/90"
                  onClick={openRespondContactCreate}
                >
                  <Plus className="size-4" />
                  Add
                </Button>
              ) : null}
            </div>
            <div className="p-6 pt-4">
              {!lead.respond_workspace_id ? (
                <p className="text-muted-foreground text-sm">
                  Set a Respond workspace on Edit lead to link inbox contacts here.
                </p>
              ) : leadRespondLinks.length === 0 ? (
                <p className="text-muted-foreground text-sm">No contacts linked to this lead yet.</p>
              ) : (
                <Sortable
                  value={leadRespondLinks}
                  onValueChange={() => {
                    // Persist only after actual drag move through onMove.
                  }}
                  getItemValue={(row) => row.id}
                  onMove={({ activeIndex, overIndex }) => {
                    const next = [...leadRespondLinks];
                    const [moved] = next.splice(activeIndex, 1);
                    next.splice(overIndex, 0, moved);
                    void saveRespondContactOrder(next)
                      .then(() => {
                        toast.success('Contact order updated');
                        void qc.invalidateQueries({ queryKey: ['commercial-lead-respond-contacts', leadId] });
                      })
                      .catch((e) => toast.error(e instanceof Error ? e.message : 'Failed to reorder contacts'));
                  }}
                  className="space-y-3"
                >
                  {leadRespondLinks.map((row) => {
                    const c = row.contact;
                    const label = [c.first_name, c.last_name].filter(Boolean).join(' ').trim() || c.name || 'Contact';
                    return (
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
                            <span className="font-semibold text-[#0a0a0a]">{label}</span>
                            {row.contact_role === 'main' ? (
                              <span className="rounded px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-[#e7000b]">
                                Main
                              </span>
                            ) : null}
                          </div>
                          <div className="mt-1 space-y-0.5 text-sm text-[#4a5565]">
                            <p>{c.phone_number?.trim() || '—'}</p>
                          </div>
                        </div>
                        {canManageRespondContacts ? (
                          <div className="flex shrink-0 items-center gap-1">
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className={cn(
                                'size-9',
                                row.contact_role === 'main'
                                  ? 'text-[#e7000b] hover:text-[#e7000b]'
                                  : 'text-muted-foreground',
                              )}
                              aria-label={row.contact_role === 'main' ? 'Main contact' : 'Mark as main contact'}
                              onClick={() => void markRespondLinkAsMain(row)}
                            >
                              <Star className={cn('size-4', row.contact_role === 'main' && 'fill-current')} />
                            </Button>
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className="size-9 text-muted-foreground"
                              aria-label="Edit contact link"
                              onClick={() => openRespondLinkEdit(row)}
                            >
                              <Pencil className="size-4" />
                            </Button>
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className="size-9 text-[#e7000b] hover:text-[#e7000b]"
                              aria-label="Remove contact link"
                              onClick={() => {
                                setRespondPendingDelete(row);
                                setRespondDeleteOpen(true);
                              }}
                            >
                              <Trash2 className="size-4" />
                            </Button>
                          </div>
                        ) : null}
                      </SortableItem>
                    );
                  })}
                </Sortable>
              )}
            </div>
          </div>
        </TabsContent>

        <TabsContent value="designs">
          <Card className="border-border/80 shadow-sm">
            <CardHeader>
              <CardTitle className="text-base font-semibold tracking-tight">Designs</CardTitle>
            </CardHeader>
            <CardContent>
              {designRows.length === 0 ? (
                <p className="text-muted-foreground text-sm">No design links stored on this lead.</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Name</TableHead>
                      <TableHead className="w-[100px]">Link</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {designRows.map((row) => (
                      <TableRow key={row.url}>
                        <TableCell>{row.name}</TableCell>
                        <TableCell>
                          <a
                            href={row.url}
                            target="_blank"
                            rel="noreferrer"
                            className="text-primary inline-flex items-center gap-1 hover:underline"
                          >
                            Open
                            <ExternalLink className="size-3" />
                          </a>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="quotations">
          <Card className="border-border/80 shadow-sm">
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle className="text-base font-semibold tracking-tight">Quotations</CardTitle>
              {canAddMq ? (
                <Button
                  type="button"
                  variant="primary"
                  size="sm"
                  className="h-9 rounded-[10px] px-4 text-sm font-medium"
                  onClick={openCreateQuotationFlow}
                >
                  + Create quotation
                </Button>
              ) : null}
            </CardHeader>
            <CardContent>
              {relatedLoading ? (
                <Skeleton className="h-24 w-full" />
              ) : !related?.quotations?.length ? (
                <p className="text-muted-foreground text-sm">No quotations yet.</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Project</TableHead>
                      <TableHead>Tender</TableHead>
                      <TableHead>Quotation</TableHead>
                      <TableHead>Title</TableHead>
                      <TableHead>Stage</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {related.quotations.map((row) => {
                      const href = `/commercial-management/quotation-revisions?tender=${encodeURIComponent(row.tender_code)}&quotation=${encodeURIComponent(row.quotation_code)}`;
                      return (
                        <TableRow
                          key={`${row.tender_code}-${row.quotation_code}`}
                          className="hover:bg-muted/50 cursor-pointer"
                          onClick={() => router.push(href)}
                        >
                          <TableCell className="max-w-[260px]">
                            <TruncatedTextCell
                              text={row.project_title}
                              dialogTitle="Project title"
                              renderLabel={(label) => (
                                <Link
                                  href={href}
                                  className="block min-w-0 font-medium text-[#e7000b] hover:underline"
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  {label}
                                </Link>
                              )}
                            />
                          </TableCell>
                          <TableCell>{row.tender_code}</TableCell>
                          <TableCell>{row.quotation_code}</TableCell>
                          <TableCell className="max-w-[260px]">
                            <TruncatedTextCell text={row.title} dialogTitle="Quotation title" />
                          </TableCell>
                          <TableCell>{row.stage_name || '—'}</TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="sales_orders">
          <Card className="border-border/80 shadow-sm">
            <CardHeader>
              <CardTitle className="text-base font-semibold tracking-tight">Sales orders</CardTitle>
            </CardHeader>
            <CardContent>
              {relatedLoading ? (
                <Skeleton className="h-24 w-full" />
              ) : !related?.sales_orders?.length ? (
                <p className="text-muted-foreground text-sm">No sales orders yet.</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Sales Order</TableHead>
                      <TableHead>Project</TableHead>
                      <TableHead>Tender</TableHead>
                      <TableHead>Title</TableHead>
                      <TableHead>Stage</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {related.sales_orders.map((row) => {
                      const href = `/commercial-management/quotation-revisions?tender=${encodeURIComponent(row.tender_code)}&quotation=${encodeURIComponent(row.quotation_code)}`;
                      return (
                        <TableRow
                          key={`${row.tender_code}-${row.quotation_code}`}
                          className="hover:bg-muted/50 cursor-pointer"
                          onClick={() => router.push(href)}
                        >
                          <TableCell className="align-middle">
                            <Link
                              href={href}
                              className="font-medium text-[#e7000b] hover:underline"
                              onClick={(e) => e.stopPropagation()}
                            >
                              {row.sales_order_code || row.quotation_code}
                            </Link>
                            {row.sales_order_code && (
                              <div className="text-xs text-[#6a7282]">Quotation ref: {row.quotation_code}</div>
                            )}
                          </TableCell>
                          <TableCell>{row.project_title || '—'}</TableCell>
                          <TableCell>{row.tender_code}</TableCell>
                          <TableCell className="max-w-[200px]">
                            <TruncatedTextCell text={row.title} dialogTitle="Title" />
                          </TableCell>
                          <TableCell>{row.stage_name || '—'}</TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="invoices">
          <Card className="border-border/80 shadow-sm">
            <CardHeader>
              <CardTitle className="text-base font-semibold tracking-tight">Orders</CardTitle>
            </CardHeader>
            <CardContent>
              {!ordersPage?.data?.length ? (
                <p className="text-muted-foreground text-sm">No order records for this client.</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Order #</TableHead>
                      <TableHead>Date</TableHead>
                      <TableHead>Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {ordersPage.data.map((o) => {
                      const href = `/order-management/orders/${o.id}`;
                      return (
                        <TableRow
                          key={o.id}
                          className="hover:bg-muted/50 cursor-pointer"
                          onClick={() => router.push(href)}
                        >
                          <TableCell>
                            <Link
                              href={href}
                              className="font-medium text-[#e7000b] hover:underline"
                              onClick={(e) => e.stopPropagation()}
                            >
                              {o.order_number}
                            </Link>
                          </TableCell>
                          <TableCell>{o.order_date ? formatDate(o.order_date) : '—'}</TableCell>
                          <TableCell>{o.order_status?.status_name || '—'}</TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="projects">
          <Card className="border-border/80 shadow-sm">
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle className="text-base font-semibold tracking-tight">Projects</CardTitle>
              {canAddProject ? (
                <Button
                  type="button"
                  variant="primary"
                  size="sm"
                  className="h-9 rounded-[10px] px-4 text-sm font-medium"
                  onClick={openProjectFlow}
                >
                  + Create project
                </Button>
              ) : null}
            </CardHeader>
            <CardContent>
              {relatedLoading ? (
                <Skeleton className="h-24 w-full" />
              ) : !related?.projects?.length ? (
                <p className="text-muted-foreground text-sm">No projects linked to this lead.</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-[#6a7282] text-xs font-medium uppercase tracking-wide">Project</TableHead>
                      <TableHead className="text-[#6a7282] text-xs font-medium uppercase tracking-wide">Lead</TableHead>
                      <TableHead className="text-[#6a7282] text-xs font-medium uppercase tracking-wide">Client Name</TableHead>
                      <TableHead className="text-[#6a7282] text-xs font-medium uppercase tracking-wide">Owner</TableHead>
                      <TableHead className="text-[#6a7282] text-xs font-medium uppercase tracking-wide">Created</TableHead>
                      <TableHead className="text-[#6a7282] text-xs font-medium uppercase tracking-wide">Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {related.projects.map((p) => {
                      const href = `/commercial-management/projects/${p.id}`;
                      return (
                        <TableRow
                          key={p.id}
                          className="hover:bg-muted/50 cursor-pointer border-b border-[#e5e7eb] last:border-b-0"
                          onClick={() => router.push(href)}
                        >
                          <TableCell className="max-w-[260px]">
                            <TruncatedTextCell
                              text={p.title}
                              dialogTitle="Project title"
                              renderLabel={(label) => (
                                <Link
                                  href={href}
                                  className="block min-w-0 font-medium text-[#e7000b] hover:underline"
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  {label}
                                </Link>
                              )}
                            />
                          </TableCell>
                          <TableCell>
                            <Link
                              href={`/commercial/leads/${lead.id}`}
                              className="font-medium text-[#e7000b] hover:underline"
                              onClick={(e) => e.stopPropagation()}
                            >
                              {lead.lead_code}
                              {typeof lead.lead_project_count === 'number' && lead.lead_project_count > 1 ? (
                                <span className="text-muted-foreground ms-1 text-xs">({lead.lead_project_count})</span>
                              ) : null}
                            </Link>
                          </TableCell>
                          <TableCell>{lead.customer_name || '—'}</TableCell>
                          <TableCell>{lead.owner_name || '—'}</TableCell>
                          <TableCell className="tabular-nums text-[#101828]">{formatDate(p.created_at)}</TableCell>
                          <TableCell>
                            <span
                              className={cn(
                                'inline-flex max-w-full truncate rounded px-2 py-1 text-xs font-medium',
                                leadProjectRowBadgeClass(p.status),
                              )}
                            >
                              {p.status || '—'}
                            </span>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="activity" className="space-y-6">
          {canEdit ? (
            <Card className="border-border/80 shadow-sm">
              <CardHeader>
                <CardTitle className="text-base font-semibold tracking-tight">Add note</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <Textarea value={noteBody} onChange={(e) => setNoteBody(e.target.value)} rows={4} />
                <Button
                  onClick={() => {
                    if (!noteBody.trim()) return;
                    addNote.mutate(noteBody.trim(), { onSuccess: () => setNoteBody('') });
                  }}
                  disabled={addNote.isPending}
                >
                  Save note
                </Button>
              </CardContent>
            </Card>
          ) : null}
          <Card className="border-border/80 shadow-sm">
            <CardHeader>
              <CardTitle className="text-base font-semibold tracking-tight">Timeline</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {mergedHistory.length === 0 ? (
                <p className="text-muted-foreground text-sm">No activity yet.</p>
              ) : (
                mergedHistory.map((h, i) => (
                  <div key={`${h.at}-${i}`} className="border-b pb-3 text-sm last:border-0">
                    <p className="text-muted-foreground text-xs">
                      {formatDate(h.at)} · {h.label}
                    </p>
                    <p className="mt-1 whitespace-pre-wrap">{h.detail}</p>
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Dialog open={convertOpen} onOpenChange={setConvertOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Convert lead</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 py-2">
            <div className="space-y-2">
              <Label>Project title</Label>
              <Input value={projectTitle} onChange={(e) => setProjectTitle(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>Tender title</Label>
              <Input value={tenderTitle} onChange={(e) => setTenderTitle(e.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConvertOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => {
                if (!projectTitle.trim() || !tenderTitle.trim()) return;
                convertLead.mutate(
                  { project_title: projectTitle.trim(), tender_title: tenderTitle.trim() },
                  {
                    onSuccess: () => {
                      setConvertOpen(false);
                      setProjectTitle('');
                      setTenderTitle('');
                    },
                  },
                );
              }}
              disabled={convertLead.isPending}
            >
              Convert
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={respondContactOpen}
        onOpenChange={(open) => {
          if (!open) closeRespondContactDialog();
        }}
      >
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {editingRespondLink ? 'Edit Respond contact link' : 'Add Respond contact'}
            </DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-2">
            {!showCreateRespondContactDialog ? (
              <div className="space-y-2">
                <Label>Search by phone or name</Label>
                <Popover open={respondContactSearchOpen} onOpenChange={setRespondContactSearchOpen}>
                  <PopoverTrigger asChild>
                    <Button
                      variant="outline"
                      type="button"
                      role="combobox"
                      className="w-full justify-between font-normal"
                    >
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
                              {respondContactSearchDebounced.trim().length > 0
                                ? 'No matches found.'
                                : 'Type at least one character...'}
                            </span>
                            {respondContactSearchDebounced.trim().length > 0 ? (
                              <Button
                                type="button"
                                variant="outline"
                                className="border-[#e7000b] text-[#e7000b] hover:bg-[#fef2f2]"
                                onClick={() => {
                                  setShowCreateRespondContactDialog(true);
                                  setRespondContactSearchOpen(false);
                                setNewRespondWorkspaceId(lead?.respond_workspace_id || '');
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
                            const optionLabel = formatRespondContactOptionLabel(h);
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
                                {pickedRespondContactId === h.id ? <Check className="ms-auto size-4 shrink-0" /> : null}
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
                      setNewRespondPhone('');
                      setNewRespondName('');
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
                  <p className="text-muted-foreground text-xs">
                    Which Respond workspace this phone number belongs to.
                  </p>
                </div>
                <div className="space-y-2">
                  <Label>Phone number</Label>
                  <Input
                    value={newRespondPhone}
                    onChange={(e) => setNewRespondPhone(e.target.value)}
                    placeholder="+60123456789"
                  />
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
                  <p className="text-muted-foreground text-xs">
                    Optional: Synced from Respond.io or set manually.
                  </p>
                </div>
              </div>
            )}

            <button
              type="button"
              className={cn(
                'flex items-center justify-between rounded-md border px-3 py-2 text-left text-sm',
                markAsMain ? 'border-[#e7000b] bg-[#fef2f2] text-[#e7000b]' : 'border-[#e5e7eb] text-[#4a5565]',
              )}
              onClick={() => setMarkAsMain((v) => !v)}
            >
              <span>Mark as main contact</span>
              <Star className={cn('size-4', markAsMain && 'fill-current')} />
            </button>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={closeRespondContactDialog}>
              Cancel
            </Button>
            <Button onClick={() => void submitRespondContactDialog()}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDeleteDialog
        open={respondDeleteOpen}
        onOpenChange={(o) => {
          setRespondDeleteOpen(o);
          if (!o) setRespondPendingDelete(null);
        }}
        description={
          respondPendingDelete
            ? 'Remove this contact link from the lead? The Respond contact record is not deleted.'
            : 'Remove this link?'
        }
        onDelete={async () => {
          if (!lead?.id || !respondPendingDelete) return;
          await deleteLeadRespondContactLink(lead.id, respondPendingDelete.id);
          void qc.invalidateQueries({ queryKey: ['commercial-lead-respond-contacts', leadId] });
          setRespondPendingDelete(null);
        }}
      />

      <ConfirmDeleteDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        description="Are you sure you want to delete this lead? This action cannot be undone."
        onDelete={async () => {
          await deleteCommercialLead(leadId);
          router.push('/commercial/leads');
        }}
      />

      <CreateQuotationDialog
        open={createQuotationOpen}
        onOpenChange={setCreateQuotationOpen}
        initialLeadId={lead.id}
        initialCustomerId={lead.customer_id || undefined}
        onCreated={() => {
          void qc.invalidateQueries({ queryKey: ['commercial-lead-related', leadId] });
          void qc.invalidateQueries({ queryKey: ['commercial-leads'] });
        }}
      />

      <Dialog
        open={projectChooserOpen}
        onOpenChange={(open) => {
          setProjectChooserOpen(open);
          if (!open) {
            setProjectPickerOpen(false);
            setProjectSearch('');
            setSelectedProjectId('');
          }
        }}
      >
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Create Project</DialogTitle>
          </DialogHeader>
          <div className="space-y-2 py-2">
            <Label>Project title</Label>
            <Popover open={projectPickerOpen} onOpenChange={setProjectPickerOpen}>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  type="button"
                  role="combobox"
                  className="w-full justify-between font-normal"
                  disabled={projectsPickerLoading}
                >
                  <span className={cn('truncate', !selectedProjectId && 'text-muted-foreground')}>
                    {selectedProjectId
                      ? availableProjectOptions.find((p) => p.id === selectedProjectId)?.title || 'Select project'
                      : projectsPickerLoading
                        ? 'Loading projects...'
                        : availableProjectOptions.length === 0
                          ? 'No projects found'
                          : 'Select existing project title...'}
                  </span>
                  <ChevronDown className="size-4 opacity-70" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-(--radix-popper-anchor-width) p-0" align="start">
                <Command shouldFilter={false}>
                  <CommandInput
                      placeholder="Search project title..."
                    value={projectSearch}
                    onValueChange={setProjectSearch}
                  />
                  <CommandList>
                    <CommandEmpty>No project title found.</CommandEmpty>
                    <CommandGroup>
                      {filteredProjectOptions.map((p) => (
                        <CommandItem
                          key={p.id}
                          value={`${p.id} ${p.title}`}
                          onSelect={() => {
                            setSelectedProjectId(p.id);
                            setProjectPickerOpen(false);
                          }}
                        >
                          <span className="truncate">{p.title}</span>
                          {selectedProjectId === p.id ? <Check className="ms-auto size-4 shrink-0" /> : null}
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
                        setProjectChooserOpen(false);
                        setCreateProjectOpen(true);
                      }}
                    >
                      + Create new project
                    </Button>
                  </div>
                ) : null}
              </PopoverContent>
            </Popover>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setProjectChooserOpen(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              disabled={!selectedProjectId}
              onClick={() => {
                if (!selectedProjectId) return;
                setProjectChooserOpen(false);
                router.push(`/commercial-management/projects/${selectedProjectId}`);
              }}
            >
              Open project
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <CreateProjectDialog
        open={createProjectOpen}
        onOpenChange={setCreateProjectOpen}
        defaultLeadId={lead.id}
        onProjectCreated={(project) => {
          void qc.invalidateQueries({ queryKey: ['commercial-lead-related', leadId] });
          void qc.invalidateQueries({ queryKey: ['commercial-leads'] });
          router.push(`/commercial-management/projects/${project.id}`);
        }}
      />

      <EntityActivitiesDock variant="lead" entityId={leadId} canPost={canEdit} />
    </div>
  );
}
