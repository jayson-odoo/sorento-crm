'use client';

import { useState } from 'react';
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
import { Switch } from '@/components/ui/switch';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import {
  createTaskCategory,
  deleteTaskCategory,
  listTaskCategories,
  updateTaskCategory,
  type CommercialTaskCategory,
} from '../services/commercialActivityPlanService';

export function TaskCategoriesPanel() {
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<CommercialTaskCategory | null>(null);
  const [deleteCode, setDeleteCode] = useState<string | null>(null);

  const [code, setCode] = useState('');
  const [label, setLabel] = useState('');
  const [sortOrder, setSortOrder] = useState('0');
  const [isActive, setIsActive] = useState(true);

  const { data: categories = [], isLoading } = useQuery({
    queryKey: ['commercial-task-categories', 'all'],
    queryFn: () => listTaskCategories(false),
  });

  const resetForm = () => {
    setCode('');
    setLabel('');
    setSortOrder(String(categories.length));
    setIsActive(true);
  };

  const openCreate = () => {
    resetForm();
    setSortOrder(String(categories.length));
    setEditing(null);
    setCreateOpen(true);
  };

  const openEdit = (row: CommercialTaskCategory) => {
    setEditing(row);
    setCode(row.code);
    setLabel(row.label);
    setSortOrder(String(row.sort_order ?? 0));
    setIsActive(row.is_active);
    setCreateOpen(true);
  };

  const createMut = useMutation({
    mutationFn: () =>
      createTaskCategory({ code: code.trim(), label: label.trim(), sort_order: parseInt(sortOrder, 10) || 0 }),
    onSuccess: () => {
      toast.success('Category created');
      setCreateOpen(false);
      void qc.invalidateQueries({ queryKey: ['commercial-task-categories'] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const updateMut = useMutation({
    mutationFn: () =>
      updateTaskCategory(editing!.code, {
        label: label.trim(),
        sort_order: parseInt(sortOrder, 10) || 0,
        is_active: isActive,
      }),
    onSuccess: () => {
      toast.success('Category updated');
      setCreateOpen(false);
      setEditing(null);
      void qc.invalidateQueries({ queryKey: ['commercial-task-categories'] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const deleteMut = useMutation({
    mutationFn: (c: string) => deleteTaskCategory(c),
    onSuccess: () => {
      toast.success('Category deleted');
      setDeleteCode(null);
      void qc.invalidateQueries({ queryKey: ['commercial-task-categories'] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const submit = () => {
    if (!label.trim()) {
      toast.error('Label is required');
      return;
    }
    if (editing) {
      updateMut.mutate();
    } else {
      if (!code.trim()) {
        toast.error('Code is required');
        return;
      }
      createMut.mutate();
    }
  };

  return (
    <div className="rounded-[10px] border border-[#e5e7eb] bg-white">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[#e5e7eb] px-6 py-6">
        <div>
          <h3 className="text-lg font-medium text-[#0a0a0a]">Task categories</h3>
          <p className="text-muted-foreground text-sm">
            Categories for grouping tasks inside templates and project boards.
          </p>
        </div>
        <Button
          type="button"
          variant="destructive"
          className="rounded-lg bg-[#e7000b] hover:bg-[#c90009]"
          onClick={openCreate}
        >
          <Plus className="size-4" />
          Add category
        </Button>
      </div>
      <div className="overflow-x-auto">
        {isLoading ? (
          <div className="p-6">
            <Skeleton className="h-32 w-full" />
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="border-b bg-[#f9fafb]">
                <TableHead className="font-medium text-[#364153]">Code</TableHead>
                <TableHead className="font-medium text-[#364153]">Label</TableHead>
                <TableHead className="font-medium text-[#364153]">Order</TableHead>
                <TableHead className="text-center font-medium text-[#364153]">Active</TableHead>
                <TableHead className="text-end font-medium text-[#364153]">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {categories.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="py-8 text-center text-sm text-muted-foreground">
                    No categories yet. Add one with the button above.
                  </TableCell>
                </TableRow>
              ) : (
                categories.map((row) => (
                  <TableRow key={row.code} className="border-b border-[#e5e7eb]">
                    <TableCell className="font-medium text-[#e7000b]">{row.code}</TableCell>
                    <TableCell className="text-[#364153]">{row.label}</TableCell>
                    <TableCell>{row.sort_order}</TableCell>
                    <TableCell className="text-center">
                      {row.is_active ? (
                        <span className="inline-flex items-center rounded-full bg-emerald-100 px-2.5 py-0.5 text-[12px] font-medium text-emerald-900">
                          Active
                        </span>
                      ) : (
                        <span className="text-muted-foreground text-sm">Inactive</span>
                      )}
                    </TableCell>
                    <TableCell className="text-end">
                      <Button type="button" variant="ghost" size="icon" onClick={() => openEdit(row)}>
                        <Pencil className="size-4" />
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="text-destructive hover:text-destructive"
                        onClick={() => setDeleteCode(row.code)}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        )}
      </div>

      <Dialog
        open={createOpen}
        onOpenChange={(o) => {
          setCreateOpen(o);
          if (!o) setEditing(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing ? 'Edit category' : 'New category'}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 py-2">
            <div className="grid gap-2">
              <Label>Code</Label>
              <Input
                value={code}
                onChange={(e) => setCode(e.target.value)}
                disabled={!!editing}
                placeholder="e.g. design"
              />
            </div>
            <div className="grid gap-2">
              <Label>Label</Label>
              <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. Design" />
            </div>
            <div className="grid gap-2">
              <Label>Sort order</Label>
              <Input
                type="number"
                value={sortOrder}
                onChange={(e) => setSortOrder(e.target.value)}
              />
            </div>
            {editing ? (
              <div className="flex items-center justify-between">
                <Label>Active</Label>
                <Switch checked={isActive} onCheckedChange={setIsActive} />
              </div>
            ) : null}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              disabled={createMut.isPending || updateMut.isPending}
              onClick={submit}
            >
              {editing ? 'Save' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDeleteDialog
        open={!!deleteCode}
        onOpenChange={(o) => !o && setDeleteCode(null)}
        description="Delete this task category?"
        onDelete={async () => {
          if (deleteCode) await deleteMut.mutateAsync(deleteCode);
        }}
      />
    </div>
  );
}
