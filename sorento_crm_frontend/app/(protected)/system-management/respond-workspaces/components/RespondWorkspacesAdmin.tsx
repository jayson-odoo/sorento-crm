'use client';

import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getCoreRowModel, useReactTable, type ColumnDef } from '@tanstack/react-table';
import { Pencil, Plus, Star, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import {
  createRespondWorkspace,
  deleteRespondWorkspace,
  listRespondWorkspaces,
  setDefaultRespondWorkspace,
  updateRespondWorkspace,
  type RespondWorkspace,
  type RespondWorkspaceCreateBody,
  type RespondWorkspaceUpdateBody,
} from '../services/respondWorkspaceService';

interface FormState {
  space_id: string;
  name: string;
  base_url: string;
  api_key: string;
  is_active: boolean;
  is_default: boolean;
}

const EMPTY_FORM: FormState = {
  space_id: '',
  name: '',
  base_url: '',
  api_key: '',
  is_active: true,
  is_default: false,
};

export default function RespondWorkspacesAdmin() {
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<RespondWorkspace | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);

  const {
    data: workspaces = [],
    isLoading,
  } = useQuery({
    queryKey: ['respond-workspaces'],
    queryFn: listRespondWorkspaces,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['respond-workspaces'] });
    queryClient.invalidateQueries({ queryKey: ['respond-workspace-select'] });
  };

  const createMutation = useMutation({
    mutationFn: createRespondWorkspace,
    onSuccess: () => {
      invalidate();
      toast.success('Workspace created');
      setDialogOpen(false);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: RespondWorkspaceUpdateBody }) =>
      updateRespondWorkspace(id, body),
    onSuccess: () => {
      invalidate();
      toast.success('Workspace updated');
      setDialogOpen(false);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteRespondWorkspace,
    onSuccess: () => {
      invalidate();
      toast.success('Workspace deleted');
      setDeleteId(null);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const setDefaultMutation = useMutation({
    mutationFn: setDefaultRespondWorkspace,
    onSuccess: () => {
      invalidate();
      toast.success('Default workspace updated');
    },
    onError: (e: Error) => toast.error(e.message),
  });

  function openCreate() {
    setEditing(null);
    setForm(EMPTY_FORM);
    setDialogOpen(true);
  }

  function openEdit(row: RespondWorkspace) {
    setEditing(row);
    setForm({
      space_id: row.space_id,
      name: row.name ?? '',
      base_url: row.base_url ?? '',
      api_key: '',
      is_active: row.is_active,
      is_default: row.is_default,
    });
    setDialogOpen(true);
  }

  function save() {
    if (editing) {
      const body: RespondWorkspaceUpdateBody = {
        space_id: form.space_id.trim(),
        name: form.name.trim() || null,
        base_url: form.base_url.trim() || null,
        is_active: form.is_active,
        is_default: form.is_default,
      };
      if (form.api_key.trim()) body.api_key = form.api_key.trim();
      updateMutation.mutate({ id: editing.id, body });
    } else {
      if (!form.space_id.trim() || !form.api_key.trim()) {
        toast.error('Space ID and API key are required');
        return;
      }
      const body: RespondWorkspaceCreateBody = {
        space_id: form.space_id.trim(),
        name: form.name.trim() || null,
        base_url: form.base_url.trim() || null,
        is_active: form.is_active,
        is_default: form.is_default,
        api_key: form.api_key.trim(),
      };
      createMutation.mutate(body);
    }
  }

  const columns = useMemo<ColumnDef<RespondWorkspace>[]>(
    () => [
      {
        id: 'name',
        accessorFn: (row) => row.name ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Name" column={column} />,
        size: 220,
        enableSorting: false,
        meta: { headerTitle: 'Name', skeleton: <Skeleton className="h-4 w-32" /> },
        cell: ({ row }) => (
          <span className="font-medium">{row.original.name || '—'}</span>
        ),
      },
      {
        id: 'space_id',
        accessorFn: (row) => row.space_id,
        header: ({ column }) => <DataGridColumnHeader title="Space ID" column={column} />,
        size: 160,
        enableSorting: false,
        meta: { headerTitle: 'Space ID', skeleton: <Skeleton className="h-4 w-24" /> },
        cell: ({ row }) => <span className="font-mono">{row.original.space_id}</span>,
      },
      {
        id: 'base_url',
        accessorFn: (row) => row.base_url ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Base URL" column={column} />,
        size: 240,
        enableSorting: false,
        meta: { headerTitle: 'Base URL', skeleton: <Skeleton className="h-4 w-40" /> },
        cell: ({ row }) => (
          <span className="truncate" title={row.original.base_url ?? ''}>
            {row.original.base_url || '—'}
          </span>
        ),
      },
      {
        id: 'api_key_masked',
        accessorFn: (row) => row.api_key_masked ?? '',
        header: ({ column }) => <DataGridColumnHeader title="API Key" column={column} />,
        size: 140,
        enableSorting: false,
        meta: { headerTitle: 'API Key', skeleton: <Skeleton className="h-4 w-20" /> },
        cell: ({ row }) => <span className="font-mono">{row.original.api_key_masked ?? '—'}</span>,
      },
      {
        id: 'is_active',
        accessorFn: (row) => row.is_active,
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        size: 110,
        enableSorting: false,
        meta: { headerTitle: 'Status', skeleton: <Skeleton className="h-6 w-16" /> },
        cell: ({ row }) =>
          row.original.is_active ? (
            <Badge variant="primary">Active</Badge>
          ) : (
            <Badge variant="secondary">Inactive</Badge>
          ),
      },
      {
        id: 'is_default',
        accessorFn: (row) => row.is_default,
        header: ({ column }) => <DataGridColumnHeader title="Default" column={column} />,
        size: 130,
        enableSorting: false,
        meta: { headerTitle: 'Default', skeleton: <Skeleton className="h-6 w-16" /> },
        cell: ({ row }) =>
          row.original.is_default ? (
            <Badge variant="primary" className="gap-1">
              <Star className="size-3 fill-current" />
              Default
            </Badge>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setDefaultMutation.mutate(row.original.id)}
              disabled={setDefaultMutation.isPending}
            >
              Set default
            </Button>
          ),
      },
      {
        id: 'actions',
        header: '',
        size: 120,
        enableSorting: false,
        enableHiding: false,
        enableResizing: false,
        cell: ({ row }) => (
          <div className="flex gap-1">
            <Button variant="ghost" size="icon" onClick={() => openEdit(row.original)} aria-label="Edit">
              <Pencil className="size-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setDeleteId(row.original.id)}
              aria-label="Delete"
            >
              <Trash2 className="size-4 text-destructive" />
            </Button>
          </div>
        ),
      },
    ],
    [setDefaultMutation],
  );

  const table = useReactTable({
    columns,
    data: workspaces,
    getRowId: (row) => row.id,
    state: { pagination: { pageIndex: 0, pageSize: 25 } },
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle>Workspaces</CardTitle>
          <Button onClick={openCreate}>
            <Plus className="size-4 mr-2" />
            Add workspace
          </Button>
        </CardHeader>
        <CardContent>
          <DataGrid
            table={table}
            recordCount={workspaces.length}
            isLoading={isLoading}
            emptyMessage="No Respond.io workspaces configured. Add one to start syncing contacts."
            tableLayout={{ width: 'fixed', columnsResizable: true }}
          >
            <DataGridTable />
          </DataGrid>
        </CardContent>
      </Card>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-[520px]">
          <DialogHeader>
            <DialogTitle>{editing ? 'Edit workspace' : 'Add workspace'}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-2">
            <div className="grid gap-2">
              <Label htmlFor="ws-name">Name</Label>
              <Input
                id="ws-name"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="e.g. Sorento Main"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="ws-space">Space ID</Label>
              <Input
                id="ws-space"
                value={form.space_id}
                onChange={(e) => setForm((f) => ({ ...f, space_id: e.target.value }))}
                placeholder="e.g. 364817"
              />
              <p className="text-xs text-muted-foreground">
                Respond.io external workspace identifier (used by MCP / sync routing).
              </p>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="ws-api">API Key {editing && <span className="text-muted-foreground">(leave blank to keep current)</span>}</Label>
              <Input
                id="ws-api"
                type="password"
                value={form.api_key}
                onChange={(e) => setForm((f) => ({ ...f, api_key: e.target.value }))}
                placeholder={editing ? '•••• (unchanged)' : 'Paste API key from Respond.io'}
                autoComplete="new-password"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="ws-base">Base URL</Label>
              <Input
                id="ws-base"
                value={form.base_url}
                onChange={(e) => setForm((f) => ({ ...f, base_url: e.target.value }))}
                placeholder="https://api.respond.io"
              />
              <p className="text-xs text-muted-foreground">
                Optional override. Defaults to the global Respond.io base URL when blank.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="ws-active"
                checked={form.is_active}
                onCheckedChange={(v) => setForm((f) => ({ ...f, is_active: v === true }))}
              />
              <Label htmlFor="ws-active">Active</Label>
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="ws-default"
                checked={form.is_default}
                onCheckedChange={(v) => setForm((f) => ({ ...f, is_default: v === true }))}
              />
              <Label htmlFor="ws-default">
                Set as default — new contacts from sync land here when no workspace is set.
              </Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={save}
              disabled={
                createMutation.isPending ||
                updateMutation.isPending ||
                !form.space_id.trim() ||
                (!editing && !form.api_key.trim())
              }
            >
              {editing ? 'Update' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!deleteId} onOpenChange={(open) => !open && setDeleteId(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete workspace</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Delete this Respond.io workspace? Contacts referencing it will have
            their workspace cleared (set to none). This action cannot be undone.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteId(null)}>
              Cancel
            </Button>
            <Button
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => deleteId && deleteMutation.mutate(deleteId)}
              disabled={deleteMutation.isPending}
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
