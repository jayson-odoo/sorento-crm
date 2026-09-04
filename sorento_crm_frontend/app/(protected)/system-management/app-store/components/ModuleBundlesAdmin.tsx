'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import type { ColumnDef } from '@tanstack/react-table';
import { useReactTable, getCoreRowModel } from '@tanstack/react-table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { SectionSkeleton } from '@/components/common/SectionSkeleton';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { useHasPermission } from '@/hooks/usePermissions';
import { TENANT_MODULES_QUERY_KEY, useTenantModules } from '@/hooks/useTenantModules';
import {
  createModuleBundle,
  deleteModuleBundle,
  fetchModuleBundles,
  updateModuleBundle,
  type ModuleBundleDTO,
} from '../services/moduleBundlesService';

const BUNDLE_KEY_PATTERN = /^[a-z][a-z0-9_]{1,62}$/;

export default function ModuleBundlesAdmin() {
  const canManage = useHasPermission('system.modules.manage');
  const queryClient = useQueryClient();
  const { raw } = useTenantModules();

  const catalogModules = useMemo(
    () =>
      [...(raw?.modules ?? [])].sort((a, b) =>
        a.display_name.localeCompare(b.display_name),
      ),
    [raw?.modules],
  );

  const bundlesQuery = useQuery({
    queryKey: ['module-bundles'],
    queryFn: fetchModuleBundles,
    enabled: canManage,
  });

  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<ModuleBundleDTO | null>(null);
  const [formKey, setFormKey] = useState('');
  const [formName, setFormName] = useState('');
  const [formSort, setFormSort] = useState('');
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());

  const [deleteTarget, setDeleteTarget] = useState<ModuleBundleDTO | null>(null);

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ['module-bundles'] });
    queryClient.invalidateQueries({ queryKey: TENANT_MODULES_QUERY_KEY });
  };

  const createMut = useMutation({
    mutationFn: createModuleBundle,
    onSuccess: () => {
      toast.success('Bundle created');
      invalidateAll();
      setEditorOpen(false);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const updateMut = useMutation({
    mutationFn: ({
      key,
      body,
    }: {
      key: string;
      body: Parameters<typeof updateModuleBundle>[1];
    }) => updateModuleBundle(key, body),
    onSuccess: () => {
      toast.success('Bundle updated');
      invalidateAll();
      setEditorOpen(false);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const deleteMut = useMutation({
    mutationFn: deleteModuleBundle,
    onSuccess: () => {
      toast.success('Bundle deleted');
      invalidateAll();
      setDeleteTarget(null);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const openCreate = () => {
    setEditing(null);
    setFormKey('');
    setFormName('');
    setFormSort('');
    setSelectedKeys(new Set());
    setEditorOpen(true);
  };

  const openEdit = (b: ModuleBundleDTO) => {
    setEditing(b);
    setFormKey(b.bundle_key);
    setFormName(b.display_name);
    setFormSort(b.sort_order ?? '');
    setSelectedKeys(new Set(b.module_keys));
    setEditorOpen(true);
  };

  const toggleKey = (mk: string) => {
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(mk)) next.delete(mk);
      else next.add(mk);
      return next;
    });
  };

  const submitEditor = () => {
    const keys = Array.from(selectedKeys);
    if (keys.length === 0) {
      toast.error('Select at least one module.');
      return;
    }
    if (!editing) {
      const bk = formKey.trim();
      if (!BUNDLE_KEY_PATTERN.test(bk)) {
        toast.error(
          'Bundle key: 2 - 63 chars, start with a letter, then lowercase letters, digits, or underscores.',
        );
        return;
      }
      const dn = formName.trim();
      if (!dn) {
        toast.error('Display name is required.');
        return;
      }
      createMut.mutate({
        bundle_key: bk,
        display_name: dn,
        module_keys: keys,
        sort_order: formSort.trim() || null,
      });
    } else {
      const dn = formName.trim();
      if (!dn) {
        toast.error('Display name is required.');
        return;
      }
      updateMut.mutate({
        key: editing.bundle_key,
        body: {
          display_name: dn,
          module_keys: keys,
          sort_order: formSort.trim() === '' ? '' : formSort.trim(),
        },
      });
    }
  };

  const busy = createMut.isPending || updateMut.isPending || deleteMut.isPending;

  const bundleColumns = useMemo<ColumnDef<ModuleBundleDTO>[]>(
    () => [
      {
        accessorKey: 'sort_order',
        header: ({ column }) => <DataGridColumnHeader title="Order" column={column} />,
        cell: ({ row }) => (
          <span className="text-muted-foreground font-mono text-xs">
            {row.original.sort_order ?? '-'}
          </span>
        ),
        size: 90,
        meta: { headerTitle: 'Order' },
      },
      {
        accessorKey: 'bundle_key',
        header: ({ column }) => <DataGridColumnHeader title="Key" column={column} />,
        cell: ({ row }) => <span className="font-mono text-xs">{row.original.bundle_key}</span>,
        size: 200,
        meta: { headerTitle: 'Key' },
      },
      {
        accessorKey: 'display_name',
        header: ({ column }) => <DataGridColumnHeader title="Display name" column={column} />,
        cell: ({ row }) => (
          <span className="truncate" title={row.original.display_name}>
            {row.original.display_name}
          </span>
        ),
        size: 240,
        meta: { headerTitle: 'Display name' },
      },
      {
        id: 'module_count',
        accessorFn: (row) => row.module_keys.length,
        header: ({ column }) => <DataGridColumnHeader title="Modules" column={column} />,
        cell: ({ row }) => row.original.module_keys.length,
        size: 100,
        meta: { headerTitle: 'Modules' },
      },
      {
        id: 'actions',
        header: () => <span className="sr-only">Actions</span>,
        cell: ({ row }) => (
          <div className="flex justify-end gap-1">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="Edit"
              onClick={(e) => {
                e.stopPropagation();
                openEdit(row.original);
              }}
              disabled={busy}
            >
              <Pencil className="size-4" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="Delete"
              onClick={(e) => {
                e.stopPropagation();
                setDeleteTarget(row.original);
              }}
              disabled={busy}
            >
              <Trash2 className="size-4 text-destructive" />
            </Button>
          </div>
        ),
        size: 120,
        enableResizing: false,
        meta: { headerTitle: 'Actions' },
      },
    ],
    [busy],
  );

  const bundlesTable = useReactTable({
    columns: bundleColumns,
    data: bundlesQuery.data ?? [],
    getRowId: (row) => row.bundle_key,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
  });

  if (!canManage) {
    return (
      <Card className="border-amber-200 bg-amber-50/50 dark:bg-amber-950/20">
        <CardHeader>
          <CardTitle className="text-base">View only</CardTitle>
          <CardDescription>
            You need <code className="text-xs">system.modules.manage</code> to manage bundles.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-2">
          <Button type="button" variant="outline" size="sm" asChild>
            <Link href="/system-management/app-store">Back to App Store</Link>
          </Button>
          <Button type="button" size="sm" onClick={openCreate}>
            <Plus className="size-4 mr-1" />
            New bundle
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Bundles</CardTitle>
        </CardHeader>
        <CardContent>
          {bundlesQuery.isLoading ? (
            <SectionSkeleton rows={4} />
          ) : bundlesQuery.error ? (
            <p className="text-sm text-destructive">Failed to load bundles.</p>
          ) : (
            <DataGrid
              table={bundlesTable}
              recordCount={(bundlesQuery.data ?? []).length}
              listingKey="system.modules.manage::bundles"
              tableLayout={{ width: 'fixed', columnsResizable: true }}
            >
              <DataGridTable />
            </DataGrid>
          )}
        </CardContent>
      </Card>

      <Dialog open={editorOpen} onOpenChange={setEditorOpen}>
        <DialogContent className="max-w-lg max-h-[90vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>{editing ? 'Edit bundle' : 'New bundle'}</DialogTitle>
            <DialogDescription>
              Choose modules to include. The installer will add any required dependencies from the
              catalog graph.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 overflow-y-auto flex-1 min-h-0 pr-1">
            {!editing && (
              <div className="space-y-2">
                <Label htmlFor="bundle-key">Bundle key</Label>
                <Input
                  id="bundle-key"
                  value={formKey}
                  onChange={(e) => setFormKey(e.target.value)}
                  placeholder="e.g. my_team_stack"
                  autoComplete="off"
                />
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="bundle-name">Display name</Label>
              <Input
                id="bundle-name"
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                placeholder="Shown in App Store dropdown"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="bundle-sort">Sort order (optional)</Label>
              <Input
                id="bundle-sort"
                value={formSort}
                onChange={(e) => setFormSort(e.target.value)}
                placeholder="e.g. 001 - lower sorts first"
              />
            </div>
            <div className="space-y-2">
              <Label>Modules in bundle</Label>
              <div className="rounded-md border p-3 max-h-[40vh] overflow-y-auto space-y-2">
                {catalogModules.map((m) => (
                  <label
                    key={m.module_key}
                    className="flex items-center gap-2 text-sm cursor-pointer"
                  >
                    <Checkbox
                      checked={selectedKeys.has(m.module_key)}
                      onCheckedChange={() => toggleKey(m.module_key)}
                    />
                    <span className="font-medium">{m.display_name}</span>
                    <span className="text-muted-foreground font-mono text-xs">({m.module_key})</span>
                  </label>
                ))}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setEditorOpen(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              onClick={submitEditor}
              disabled={busy}
            >
              {editing
                ? updateMut.isPending
                  ? 'Saving…'
                  : 'Save bundle'
                : createMut.isPending
                  ? 'Creating…'
                  : 'Create bundle'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete bundle &quot;{deleteTarget?.display_name}&quot;?</AlertDialogTitle>
            <AlertDialogDescription>
              This only removes the preset from the database. It does not uninstall modules from
              your tenant.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel type="button">Cancel</AlertDialogCancel>
            <Button
              type="button"
              variant="destructive"
              disabled={deleteMut.isPending}
              onClick={() => deleteTarget && deleteMut.mutate(deleteTarget.bundle_key)}
            >
              {deleteMut.isPending ? 'Deleting…' : 'Delete'}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
