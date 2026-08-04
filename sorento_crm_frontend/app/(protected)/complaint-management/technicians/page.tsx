'use client';

/**
 * Technicians - the people who attend a site, and deliberately not users.
 *
 * No account is ever created here (AC-F8). A technician is reached on WhatsApp through a
 * portal link, which is the premise the whole clocks decision rests on: form SLA resolves
 * assignees through agent teams -> team members -> users, so giving somebody a login would
 * quietly put them back inside an engine that cannot schedule them.
 *
 * `employment_type` exists because the discovery study shows the role blurring - an
 * outstation technician is often somebody else's staff - so modelling only employees would
 * make the ordinary case unstorable.
 *
 * Delete is hard, with a confirmation. Past assignments survive it: the FK is ON DELETE SET
 * NULL, so removing somebody who left does not erase the record that a visit happened.
 */

import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Edit, Plus, Search, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import {
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from '@tanstack/react-table';

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
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar } from '@/components/ui/data-grid-list-toolbar';
import { DataGridTable } from '@/components/ui/data-grid-table';
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
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { SearchableSelect } from '@/components/common/SearchableSelect';

import {
  createTechnician,
  deleteTechnician,
  listTechnicians,
  updateTechnician,
  type Technician,
} from '../service-jobs/services/serviceJobService';

const EMPLOYMENT_OPTIONS = [
  { value: 'employee', label: 'Employee' },
  { value: 'contractor', label: 'Contractor' },
];

interface FormState {
  name: string;
  phone: string;
  employment_type: string;
}

const EMPTY: FormState = { name: '', phone: '', employment_type: '' };

export default function TechniciansPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Technician | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY);
  const [toDelete, setToDelete] = useState<Technician | null>(null);

  const list = useQuery({
    queryKey: ['service-job-technicians-all'],
    queryFn: () => listTechnicians(),
  });

  const rows = useMemo(
    () =>
      (list.data ?? []).filter((row) =>
        row.name.toLowerCase().includes(search.trim().toLowerCase()),
      ),
    [list.data, search],
  );

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['service-job-technicians-all'] });
    queryClient.invalidateQueries({ queryKey: ['service-job-technicians'] });
  };

  const save = useMutation({
    mutationFn: () => {
      const payload = {
        name: form.name.trim(),
        phone: form.phone.trim() || null,
        employment_type: form.employment_type || null,
      };
      return editing ? updateTechnician(editing.id, payload) : createTechnician(payload);
    },
    onSuccess: () => {
      toast.success(editing ? 'Technician updated.' : 'Technician added.');
      setFormOpen(false);
      setEditing(null);
      setForm(EMPTY);
      invalidate();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteTechnician(id),
    onSuccess: () => {
      toast.success('Technician deleted.');
      setToDelete(null);
      invalidate();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const openEdit = (row: Technician) => {
    setEditing(row);
    setForm({
      name: row.name,
      phone: row.phone ?? '',
      employment_type: row.employment_type ?? '',
    });
    setFormOpen(true);
  };

  const columns = useMemo<ColumnDef<Technician>[]>(
    () => [
      {
        id: 'name',
        accessorFn: (row) => row.name,
        header: ({ column }) => <DataGridColumnHeader title="Name" column={column} />,
        size: 280,
        meta: { headerTitle: 'Name' },
        cell: ({ row }) => (
          <span className="block truncate font-medium" title={row.original.name}>
            {row.original.name}
          </span>
        ),
      },
      {
        id: 'phone',
        accessorFn: (row) => row.phone,
        header: ({ column }) => <DataGridColumnHeader title="Phone" column={column} />,
        size: 200,
        enableSorting: false,
        meta: { headerTitle: 'Phone' },
        cell: ({ row }) => (
          <span className="block truncate text-muted-foreground">{row.original.phone ?? '-'}</span>
        ),
      },
      {
        id: 'employment_type',
        accessorFn: (row) => row.employment_type,
        header: ({ column }) => <DataGridColumnHeader title="Engagement" column={column} />,
        size: 180,
        enableSorting: false,
        meta: { headerTitle: 'Engagement' },
        cell: ({ row }) => (
          <span className="block truncate capitalize text-muted-foreground">
            {row.original.employment_type ?? '-'}
          </span>
        ),
      },
      {
        id: 'is_active',
        accessorFn: (row) => row.is_active,
        header: ({ column }) => <DataGridColumnHeader title="Active" column={column} />,
        size: 140,
        enableSorting: false,
        meta: { headerTitle: 'Active' },
        cell: ({ row }) => (
          <Badge
            variant={row.original.is_active ? 'success' : 'secondary'}
            size="sm"
            appearance="ghost"
            className="shrink-0"
          >
            <BadgeDot />
            {row.original.is_active ? 'Active' : 'Inactive'}
          </Badge>
        ),
      },
      {
        id: 'actions',
        header: '',
        size: 110,
        enableSorting: false,
        enableHiding: false,
        enableResizing: false,
        meta: { headerTitle: 'Actions' },
        cell: ({ row }) => (
          <div className="flex items-center gap-1">
            <Button
              mode="icon"
              variant="ghost"
              size="sm"
              title="Edit"
              onClick={() => openEdit(row.original)}
            >
              <Edit className="size-4" />
            </Button>
            <Button
              mode="icon"
              variant="ghost"
              size="sm"
              title="Delete"
              onClick={() => setToDelete(row.original)}
            >
              <Trash2 className="size-4" />
            </Button>
          </div>
        ),
      },
    ],
    [],
  );

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.id,
    columnResizeMode: 'onChange',
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold break-words">Technicians</h1>
        <p className="text-sm text-muted-foreground">
          The people who attend a site. They are reached on WhatsApp, never through a login, so
          adding one here creates no user account.
        </p>
      </div>

      <DataGrid
        table={table}
        recordCount={rows.length}
        isLoading={list.isLoading}
        tableLayout={{ width: 'fixed', columnsResizable: true }}
      >
        <Card>
          <CardHeader className="block">
            <DataGridListToolbar
              table={table}
              searchSlot={
                <div className="relative">
                  <Search className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    placeholder="Search technicians..."
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    className="w-64 ps-9"
                  />
                </div>
              }
              primaryAction={
                <Button
                  onClick={() => {
                    setEditing(null);
                    setForm(EMPTY);
                    setFormOpen(true);
                  }}
                >
                  <Plus className="size-4" />
                  Add Technician
                </Button>
              }
            />
          </CardHeader>
          <CardTable>
            <ScrollArea>
              {rows.length === 0 && !list.isLoading ? (
                <div className="py-8 text-center text-sm text-muted-foreground">
                  No technicians yet. Add one before assigning work on the dispatch board.
                </div>
              ) : (
                <DataGridTable />
              )}
              <ScrollBar orientation="horizontal" />
            </ScrollArea>
          </CardTable>
        </Card>
      </DataGrid>

      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing ? 'Edit technician' : 'Add technician'}</DialogTitle>
            <DialogDescription>
              No login is created. The phone is how they receive their job link.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4">
            <div>
              <Label htmlFor="technician-name">Name</Label>
              <Input
                id="technician-name"
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
              />
            </div>
            <div>
              <Label htmlFor="technician-phone">Phone</Label>
              <Input
                id="technician-phone"
                placeholder="+60..."
                value={form.phone}
                onChange={(event) => setForm({ ...form, phone: event.target.value })}
              />
            </div>
            <div>
              <Label htmlFor="technician-engagement">Engagement</Label>
              <SearchableSelect
                id="technician-engagement"
                clearable
                value={form.employment_type}
                onChange={(value) => setForm({ ...form, employment_type: value })}
                options={EMPLOYMENT_OPTIONS}
                placeholder="Employee or contractor"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setFormOpen(false)}>
              Cancel
            </Button>
            <Button disabled={!form.name.trim() || save.isPending} onClick={() => save.mutate()}>
              {editing ? 'Save' : 'Add'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={Boolean(toDelete)} onOpenChange={(open) => !open && setToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Confirm delete</AlertDialogTitle>
            <AlertDialogDescription>
              This action cannot be undone. Past assignments stay on their jobs, so the record
              that a visit happened survives, but {toDelete?.name} will no longer be assignable.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => toDelete && remove.mutate(toDelete.id)}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
