'use client';

import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import Link from 'next/link';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import {
  createTemplateNode,
  deleteTemplateNode,
  getRuntimeActivityTemplate,
  listActivityTaskStatuses,
  listTaskCategories,
  updateTemplateNode,
  type TemplateNodeTree,
} from '../services/commercialActivityPlanService';

function flattenNodesForParentSelect(nodes: TemplateNodeTree[], depth = 0): { id: string; label: string }[] {
  const out: { id: string; label: string }[] = [];
  for (const n of nodes) {
    if (depth === 0) out.push({ id: n.id, label: n.title });
    if (n.children?.length) out.push(...flattenNodesForParentSelect(n.children, depth + 1));
  }
  return out;
}

function flattenTaskTableRows(nodes: TemplateNodeTree[], depth = 0): { node: TemplateNodeTree; depth: number }[] {
  const out: { node: TemplateNodeTree; depth: number }[] = [];
  for (const n of nodes) {
    out.push({ node: n, depth });
    if (n.children?.length) out.push(...flattenTaskTableRows(n.children, depth + 1));
  }
  return out;
}

function NodeRows({
  nodes,
  depth,
  onRequestDelete,
  onAddSubtask,
}: {
  nodes: TemplateNodeTree[];
  depth: number;
  onRequestDelete: (id: string) => void;
  onAddSubtask: (id: string) => void;
}) {
  return (
    <>
      {nodes.map((n) => (
        <div key={n.id}>
          <div
            className="flex flex-wrap items-start justify-between gap-2 border-b py-2 text-sm last:border-0"
            style={{ paddingInlineStart: depth * 12 }}
          >
            <div>
              <div className="font-medium">{n.title}</div>
              <div className="text-muted-foreground text-xs">
                {n.category_code ? `${n.category_code}` : ''}
                {n.is_service_task ? ' · service' : ''}
                {n.sort_order != null ? ` · order ${n.sort_order}` : ''}
              </div>
            </div>
            <Button type="button" variant="ghost" size="icon" onClick={() => onRequestDelete(n.id)}>
              <Trash2 className="size-4" />
            </Button>
            {depth === 0 ? (
              <Button type="button" variant="ghost" size="icon" onClick={() => onAddSubtask(n.id)}>
                <Plus className="size-4" />
              </Button>
            ) : null}
          </div>
          {n.children?.length ? (
            <NodeRows nodes={n.children} depth={depth + 1} onRequestDelete={onRequestDelete} onAddSubtask={onAddSubtask} />
          ) : null}
        </div>
      ))}
    </>
  );
}

type Layout = 'tree' | 'table';

export function RuntimeTemplateTasksPanel({
  templateId,
  open,
  layout = 'tree',
  showAdvancedLink = true,
  accentActions = false,
}: {
  templateId: string;
  open: boolean;
  layout?: Layout;
  showAdvancedLink?: boolean;
  /** Red primary actions (Configuration / Project Tasks tab). */
  accentActions?: boolean;
}) {
  const qc = useQueryClient();
  const [nodeDeleteId, setNodeDeleteId] = useState<string | null>(null);
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['commercial-activity-template', templateId],
    queryFn: () => getRuntimeActivityTemplate(templateId),
    enabled: open,
  });

  const { data: categories = [] } = useQuery({
    queryKey: ['commercial-task-categories'],
    queryFn: () => listTaskCategories(true),
    enabled: open,
  });

  const { data: statuses = [] } = useQuery({
    queryKey: ['commercial-activity-statuses', 'tpl'],
    queryFn: () => listActivityTaskStatuses(true),
    enabled: open,
  });

  const [addOpen, setAddOpen] = useState(false);
  const [editingNodeId, setEditingNodeId] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [categoryCode, setCategoryCode] = useState('');
  const [sortOrder, setSortOrder] = useState(0);
  const [isService, setIsService] = useState(false);
  const [parentId, setParentId] = useState<string>('__root__');
  const [defaultStatusId, setDefaultStatusId] = useState<string>('');
  const [leadTimeDays, setLeadTimeDays] = useState<number>(1);
  const [dependencyNodeIds, setDependencyNodeIds] = useState<string[]>([]);

  const flatParents = useMemo(() => flattenNodesForParentSelect(data?.nodes ?? []), [data?.nodes]);
  const flatRows = useMemo(() => flattenTaskTableRows(data?.nodes ?? []), [data?.nodes]);
  const dependencyOptions = useMemo(
    () => flatRows.map(({ node }) => ({ id: node.id, title: node.title })),
    [flatRows],
  );
  const resetForm = () => {
    setTitle('');
    setDescription('');
    setCategoryCode('');
    setSortOrder(0);
    setIsService(false);
    setParentId('__root__');
    setDefaultStatusId('');
    setLeadTimeDays(1);
    setDependencyNodeIds([]);
  };

  const openAddDialog = (nextParentId: string = '__root__') => {
    resetForm();
    setEditingNodeId(null);
    setParentId(nextParentId);
    setAddOpen(true);
  };

  const openEditDialog = (n: TemplateNodeTree) => {
    setEditingNodeId(n.id);
    setTitle(n.title || '');
    setDescription(n.description || '');
    setCategoryCode(n.category_code || '');
    setSortOrder(n.sort_order ?? 0);
    setIsService(!!n.is_service_task);
    setParentId(n.parent_id || '__root__');
    setDefaultStatusId(n.default_status_id || '');
    setLeadTimeDays(n.lead_time_days ?? 1);
    setDependencyNodeIds([...(n.dependency_node_ids ?? [])]);
    setAddOpen(true);
  };


  const categoryLabel = (code: string | null | undefined) => {
    if (!code) return null;
    return categories.find((c) => c.code === code)?.label ?? code;
  };

  const deleteNodeMut = useMutation({
    mutationFn: (nodeId: string) => deleteTemplateNode(templateId, nodeId),
    onSuccess: () => {
      toast.success('Task removed');
      setNodeDeleteId(null);
      void refetch();
      void qc.invalidateQueries({ queryKey: ['commercial-activity-templates-runtime'] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const addMut = useMutation({
    mutationFn: () =>
      createTemplateNode(templateId, {
        title: title.trim(),
        description: description.trim() || null,
        category_code: categoryCode || null,
        is_service_task: isService,
        sort_order: sortOrder,
        parent_id: parentId === '__root__' ? null : parentId,
        default_status_id: defaultStatusId || null,
        lead_time_days: Math.max(1, leadTimeDays || 1),
        dependency_node_ids: dependencyNodeIds,
      }),
    onSuccess: () => {
      toast.success('Task added');
      setAddOpen(false);
      resetForm();
      void refetch();
      void qc.invalidateQueries({ queryKey: ['commercial-activity-templates-runtime'] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const updateMut = useMutation({
    mutationFn: () =>
      updateTemplateNode(templateId, editingNodeId!, {
        title: title.trim(),
        description: description.trim() || null,
        category_code: categoryCode || null,
        is_service_task: isService,
        sort_order: sortOrder,
        parent_id: parentId === '__root__' ? null : parentId,
        default_status_id: defaultStatusId || null,
        lead_time_days: Math.max(1, leadTimeDays || 1),
        dependency_node_ids: dependencyNodeIds,
      }),
    onSuccess: () => {
      toast.success('Task updated');
      setAddOpen(false);
      setEditingNodeId(null);
      resetForm();
      void refetch();
      void qc.invalidateQueries({ queryKey: ['commercial-activity-templates-runtime'] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const submitTask = () => {
    if (!title.trim()) return;
    if (editingNodeId) updateMut.mutate();
    else addMut.mutate();
  };

  if (!open) return null;
  if (isLoading || !data) {
    return <Skeleton className="h-24 w-full" />;
  }

  return (
    <div className="space-y-4 pt-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button
          type="button"
          size="sm"
          variant={accentActions ? 'destructive' : 'primary'}
          onClick={() => openAddDialog('__root__')}
        >
          <Plus className="size-4" />
          Add task
        </Button>
        {showAdvancedLink ? (
          <Button type="button" variant="link" size="sm" className="text-muted-foreground h-auto p-0" asChild>
            <Link href="/commercial-core/process-configuration/activity-templates">Nested editor…</Link>
          </Button>
        ) : null}
      </div>
      {!data.nodes?.length ? (
        <p className="text-muted-foreground text-sm">No tasks in this template yet.</p>
      ) : layout === 'table' ? (
        <div className="overflow-x-auto rounded-md border">
          <Table>
            <TableHeader>
              <TableRow className="border-b bg-[#f9fafb]">
                <TableHead className="text-[#364153]">Task</TableHead>
                <TableHead className="text-[#364153]">Description</TableHead>
                <TableHead className="w-[140px] text-[#364153]">Category</TableHead>
                <TableHead className="w-[100px] text-end text-[#364153]">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {flatRows.map(({ node: n, depth }) => (
                <TableRow key={n.id} className="border-b">
                  <TableCell className="align-top font-medium" style={{ paddingInlineStart: 16 + depth * 12 }}>
                    {n.title}
                  </TableCell>
                  <TableCell className="text-muted-foreground max-w-md align-top text-sm">
                    {n.description?.trim() || '—'}
                  </TableCell>
                  <TableCell className="align-top">
                    {n.category_code ? (
                      <Badge variant="secondary" className="border-0 bg-[#155dfc]/15 font-medium text-[#155dfc] hover:bg-[#155dfc]/20">
                        {categoryLabel(n.category_code)}
                      </Badge>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell className="text-end align-top">
                    {depth === 0 ? (
                      <Button type="button" variant="ghost" size="icon" aria-label="Add subtask" onClick={() => openAddDialog(n.id)}>
                        <Plus className="size-4" />
                      </Button>
                    ) : null}
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      aria-label="Edit task"
                      onClick={() => openEditDialog(n)}
                    >
                      <Pencil className="size-4" />
                    </Button>
                    <Button type="button" variant="ghost" size="icon" onClick={() => setNodeDeleteId(n.id)}>
                      <Trash2 className="size-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : (
        <NodeRows nodes={data.nodes} depth={0} onRequestDelete={setNodeDeleteId} onAddSubtask={openAddDialog} />
      )}

      <ConfirmDeleteDialog
        open={!!nodeDeleteId}
        onOpenChange={(o) => !o && setNodeDeleteId(null)}
        description="Remove this task from the template?"
        onDelete={async () => {
          if (nodeDeleteId) await deleteNodeMut.mutateAsync(nodeDeleteId);
        }}
      />

      <Dialog
        open={addOpen}
        onOpenChange={(o) => {
          setAddOpen(o);
          if (!o) {
            setEditingNodeId(null);
            resetForm();
          }
        }}
      >
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{editingNodeId ? 'Edit task' : 'Add task'}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 py-2">
            <div className="grid gap-2">
              <Label>Title</Label>
              <Input value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div className="grid gap-2">
              <Label>Description</Label>
              <Input value={description} onChange={(e) => setDescription(e.target.value)} />
            </div>
            <div className="grid gap-2">
              <Label>Parent</Label>
              <Select value={parentId} onValueChange={setParentId}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__root__">(root)</SelectItem>
                  {flatParents.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-muted-foreground text-xs">Only one subtask level is allowed.</p>
            </div>
            <div className="grid gap-2">
              <Label>Category</Label>
              <Select value={categoryCode || '__none__'} onValueChange={(v) => setCategoryCode(v === '__none__' ? '' : v)}>
                <SelectTrigger>
                  <SelectValue placeholder="Optional" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">—</SelectItem>
                  {categories.map((c) => (
                    <SelectItem key={c.code} value={c.code}>
                      {c.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="grid gap-2">
                <Label>Sort order</Label>
                <Input type="number" value={sortOrder} onChange={(e) => setSortOrder(Number(e.target.value))} />
              </div>
              <div className="grid gap-2">
                <Label>Default status</Label>
                <Select
                  value={defaultStatusId || '__none__'}
                  onValueChange={(v) => setDefaultStatusId(v === '__none__' ? '' : v)}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Optional" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">—</SelectItem>
                    {statuses.map((s) => (
                      <SelectItem key={s.id} value={s.id}>
                        {s.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid gap-2">
              <Label>Lead time (working days)</Label>
              <Input type="number" min={1} value={leadTimeDays} onChange={(e) => setLeadTimeDays(Number(e.target.value) || 1)} />
            </div>
            <div className="grid gap-2">
              <Label>Depends on</Label>
              {!dependencyOptions.length ? (
                <p className="text-muted-foreground text-xs">No existing tasks to depend on yet.</p>
              ) : (
                <div className="max-h-32 space-y-1 overflow-y-auto rounded-md border p-2">
                  {dependencyOptions.map((opt) => {
                    const checked = dependencyNodeIds.includes(opt.id);
                    return (
                      <label key={opt.id} className="flex items-center gap-2 text-sm">
                        <Checkbox
                          checked={checked}
                          onCheckedChange={(v) =>
                            setDependencyNodeIds((prev) =>
                              v ? [...prev, opt.id] : prev.filter((id) => id !== opt.id),
                            )
                          }
                        />
                        <span>{opt.title}</span>
                      </label>
                    );
                  })}
                </div>
              )}
            </div>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox checked={isService} onCheckedChange={(v) => setIsService(!!v)} />
              Service task
            </label>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setAddOpen(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              disabled={!title.trim() || addMut.isPending || updateMut.isPending}
              onClick={submitTask}
            >
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
