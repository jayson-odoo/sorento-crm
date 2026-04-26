'use client';

import { useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
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
import { Skeleton } from '@/components/ui/skeleton';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { RuntimeTemplateTasksPanel } from '../RuntimeTemplateTasksPanel';
import { TaskCategoriesPanel } from '../TaskCategoriesPanel';
import {
  createRuntimeActivityTemplate,
  deleteRuntimeActivityTemplate,
  listRuntimeActivityTemplates,
  updateRuntimeActivityTemplate,
  type ActivityTemplateScope,
  type RuntimeTemplateSummary,
} from '../../services/commercialActivityPlanService';

export function ConfigurationProjectTasksTab() {
  const searchParams = useSearchParams();
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [newScope, setNewScope] = useState<ActivityTemplateScope>('project');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [deleteTplId, setDeleteTplId] = useState<string | null>(null);
  const [renameTpl, setRenameTpl] = useState<RuntimeTemplateSummary | null>(null);
  const [renameValue, setRenameValue] = useState('');

  const { data: templates = [], isLoading } = useQuery({
    queryKey: ['commercial-activity-templates-runtime'],
    queryFn: () => listRuntimeActivityTemplates(true),
  });

  useEffect(() => {
    if (!templates.length) {
      setSelectedId(null);
      return;
    }
    const deep = searchParams.get('ttpl');
    if (deep && templates.some((t) => t.id === deep)) {
      setSelectedId(deep);
      return;
    }
    if (!selectedId || !templates.some((t) => t.id === selectedId)) {
      setSelectedId(templates[0].id);
    }
  }, [templates, selectedId, searchParams]);

  const createMut = useMutation({
    mutationFn: () =>
      createRuntimeActivityTemplate({ name: newName.trim(), is_active: true, template_scope: newScope }),
    onSuccess: (tpl) => {
      toast.success('Template created');
      setCreateOpen(false);
      setNewName('');
      setNewScope('project');
      setSelectedId(tpl.id);
      void qc.invalidateQueries({ queryKey: ['commercial-activity-templates-runtime'] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteRuntimeActivityTemplate(id),
    onSuccess: () => {
      toast.success('Template deleted');
      setDeleteTplId(null);
      setSelectedId(null);
      void qc.invalidateQueries({ queryKey: ['commercial-activity-templates-runtime'] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const renameMut = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      updateRuntimeActivityTemplate(id, { name }),
    onSuccess: () => {
      toast.success('Template renamed');
      setRenameTpl(null);
      void qc.invalidateQueries({ queryKey: ['commercial-activity-templates-runtime'] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const selected = templates.find((t) => t.id === selectedId);

  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
      <div className="w-full shrink-0 rounded-[10px] border border-[#e5e7eb] bg-white p-6 lg:w-[411px]">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-medium text-[#0a0a0a]">Templates</h3>
          <Button
            type="button"
            size="icon"
            variant="destructive"
            className="size-8 rounded-lg bg-[#e7000b] hover:bg-[#c90009]"
            onClick={() => setCreateOpen(true)}
          >
            <Plus className="size-4" />
          </Button>
        </div>
        {isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : templates.length === 0 ? (
          <p className="text-muted-foreground text-sm">No templates yet. Create one with +.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {templates.map((t) => {
              const active = t.id === selectedId;
              return (
                <div
                  key={t.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => setSelectedId(t.id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      setSelectedId(t.id);
                    }
                  }}
                  className={cn(
                    'flex w-full cursor-pointer items-start justify-between gap-2 rounded-lg border p-3 text-start transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring',
                    active
                      ? 'border-[#e7000b] bg-[#fef2f2]'
                      : 'border-transparent bg-white hover:bg-muted/30',
                  )}
                >
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-medium text-[#0a0a0a]">{t.name}</p>
                      <Badge variant="secondary" className="text-[10px] font-normal">
                        {(t.template_scope || 'project') === 'quotation' ? 'Quotation' : 'Project'}
                      </Badge>
                    </div>
                    <p className="text-muted-foreground text-xs">v{t.version_number}</p>
                  </div>
                  <div className="flex gap-1">
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="size-8"
                      onClick={(e) => {
                        e.stopPropagation();
                        setRenameTpl(t);
                        setRenameValue(t.name);
                      }}
                    >
                      <span className="sr-only">Rename template</span>
                      <Pencil className="size-4" />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="size-8 text-destructive hover:text-destructive"
                      onClick={(e) => {
                        e.stopPropagation();
                        setDeleteTplId(t.id);
                      }}
                    >
                      <span className="sr-only">Delete template</span>
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="min-w-0 flex-1 space-y-6">
        {selected ? (
          <div className="rounded-[10px] border border-[#e5e7eb] bg-white">
            <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[#e5e7eb] px-6 py-6">
              <div>
                <h3 className="text-lg font-medium text-[#0a0a0a]">{selected.name}</h3>
                <p className="text-muted-foreground text-sm">Configure tasks that apply when this template is used.</p>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  setRenameTpl(selected);
                  setRenameValue(selected.name);
                }}
              >
                <Pencil className="size-4" />
                Rename
              </Button>
            </div>
            <div className="px-6 pb-6">
              <RuntimeTemplateTasksPanel
                templateId={selected.id}
                open={!!selected.id}
                layout="table"
                accentActions
                showAdvancedLink
              />
            </div>
          </div>
        ) : null}
        <TaskCategoriesPanel />
      </div>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New template</DialogTitle>
          </DialogHeader>
          <div className="grid gap-2 py-2">
            <Label>Name</Label>
            <Input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="e.g. Standard delivery" />
            <Label className="pt-2">Use for</Label>
            <RadioGroup
              value={newScope}
              onValueChange={(v) => setNewScope(v as ActivityTemplateScope)}
              className="flex flex-col gap-2"
            >
              <label className="flex cursor-pointer items-center gap-2 text-sm">
                <RadioGroupItem value="project" id="scope-project" />
                <span>Project</span>
              </label>
              <label className="flex cursor-pointer items-center gap-2 text-sm">
                <RadioGroupItem value="quotation" id="scope-quotation" />
                <span>Quotation</span>
              </label>
            </RadioGroup>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button type="button" disabled={!newName.trim() || createMut.isPending} onClick={() => createMut.mutate()}>
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDeleteDialog
        open={!!deleteTplId}
        onOpenChange={(o) => !o && setDeleteTplId(null)}
        description="Delete this template and all of its tasks?"
        onDelete={async () => {
          if (deleteTplId) await deleteMut.mutateAsync(deleteTplId);
        }}
      />

      <Dialog open={!!renameTpl} onOpenChange={(o) => !o && setRenameTpl(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rename template</DialogTitle>
          </DialogHeader>
          <div className="grid gap-2 py-2">
            <Label>Name</Label>
            <Input
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              autoFocus
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setRenameTpl(null)}>
              Cancel
            </Button>
            <Button
              type="button"
              disabled={!renameValue.trim() || renameMut.isPending}
              onClick={() => {
                if (renameTpl) renameMut.mutate({ id: renameTpl.id, name: renameValue.trim() });
              }}
            >
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
