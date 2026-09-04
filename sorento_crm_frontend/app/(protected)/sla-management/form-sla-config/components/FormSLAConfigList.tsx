'use client';

import { useMemo, useState } from 'react';
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import type { ColumnDef } from '@tanstack/react-table';
import { Plus, Pencil, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
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
import { Skeleton } from '@/components/ui/skeleton';
import { PanelDataGrid } from '@/components/common/PanelDataGrid';
import { toast } from '@/lib/toast';
import {
  listFormSLAConfigs,
  deleteFormSLAConfig,
  FORM_SLA_TYPE_LABELS,
  type FormSLAConfig,
  type FormSLASourceType,
} from '../../_shared/formSLAService';
import FormSLAConfigDialog from './FormSLAConfigDialog';

function EventChips({ value }: { value: string | null | undefined }) {
  if (!value) return <> - </>;
  const events = value.split(',').map((s) => s.trim()).filter(Boolean);
  if (events.length === 0) return <> - </>;
  return (
    <div className="flex flex-wrap gap-1">
      {events.map((e) => (
        <code
          key={e}
          className="rounded bg-muted px-1.5 py-0.5 text-xs"
        >
          {e}
        </code>
      ))}
    </div>
  );
}

export default function FormSLAConfigList() {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<FormSLAConfig | null>(null);
  const [creating, setCreating] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<FormSLAConfig | null>(null);

  const queryKey = ['form-sla-configs'] as const;
  const { data, isLoading, error } = useQuery({
    queryKey,
    queryFn: () => listFormSLAConfigs(),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteFormSLAConfig(id),
    onSuccess: () => {
      toast.success('Configuration deleted');
      queryClient.invalidateQueries({ queryKey });
      setDeleteTarget(null);
    },
    onError: (e: Error) => {
      toast.error(e.message || 'Delete failed');
    },
  });

  const grouped = useMemo(() => {
    const map = new Map<FormSLASourceType, FormSLAConfig[]>();
    (data || []).forEach((c) => {
      const arr = map.get(c.source_entity_type as FormSLASourceType) || [];
      arr.push(c);
      map.set(c.source_entity_type as FormSLASourceType, arr);
    });
    return map;
  }, [data]);

  const columns = useMemo<ColumnDef<FormSLAConfig>[]>(
    () => [
      {
        accessorKey: 'stage_code',
        header: ({ column }) => <DataGridColumnHeader title="Stage" column={column} />,
        cell: ({ row }) => <span className="font-medium">{row.original.stage_code}</span>,
        size: 130,
        meta: { headerTitle: 'Stage' },
      },
      {
        id: 'policy',
        // A policy row with neither a name nor a code says so. The first eight
        // characters of its UUID told the reader nothing they could act on,
        // and no UUID renders in the UI.
        accessorFn: (row) => row.policy_name || row.policy_code || '',
        header: ({ column }) => <DataGridColumnHeader title="Policy" column={column} />,
        cell: ({ row }) =>
          row.original.policy_name || row.original.policy_code || (
            <span className="text-muted-foreground">(unnamed policy)</span>
          ),
        size: 170,
        meta: { headerTitle: 'Policy' },
      },
      {
        accessorKey: 'agent_code',
        header: ({ column }) => <DataGridColumnHeader title="Agent" column={column} />,
        size: 130,
        meta: { headerTitle: 'Agent' },
      },
      {
        id: 'team_set_code',
        accessorFn: (row) => row.team_set_code || '',
        header: ({ column }) => <DataGridColumnHeader title="Team set" column={column} />,
        cell: ({ row }) => row.original.team_set_code || '-',
        size: 130,
        meta: { headerTitle: 'Team set' },
      },
      {
        accessorKey: 'start_event',
        header: ({ column }) => <DataGridColumnHeader title="Start" column={column} />,
        cell: ({ row }) => (
          <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
            {row.original.start_event}
          </code>
        ),
        size: 150,
        meta: { headerTitle: 'Start' },
      },
      {
        id: 'respond_event',
        accessorFn: (row) => row.respond_event || '',
        header: ({ column }) => <DataGridColumnHeader title="Respond" column={column} />,
        cell: ({ row }) => <EventChips value={row.original.respond_event} />,
        size: 170,
        meta: { headerTitle: 'Respond' },
      },
      {
        id: 'resolve_event',
        accessorFn: (row) => row.resolve_event || '',
        header: ({ column }) => <DataGridColumnHeader title="Resolve" column={column} />,
        cell: ({ row }) => <EventChips value={row.original.resolve_event} />,
        size: 170,
        meta: { headerTitle: 'Resolve' },
      },
      {
        id: 'next_stage_code',
        accessorFn: (row) => row.next_stage_code || '',
        header: ({ column }) => <DataGridColumnHeader title="Next stage" column={column} />,
        cell: ({ row }) =>
          row.original.next_stage_code ? (
            <Badge variant="outline">{row.original.next_stage_code}</Badge>
          ) : (
            '-'
          ),
        size: 130,
        meta: { headerTitle: 'Next stage' },
      },
      {
        accessorKey: 'is_active',
        header: ({ column }) => <DataGridColumnHeader title="Active" column={column} />,
        cell: ({ row }) =>
          row.original.is_active ? (
            <Badge variant="outline" className="border-emerald-300 text-emerald-700">
              Active
            </Badge>
          ) : (
            <Badge variant="outline" className="border-slate-300 text-slate-500">
              Inactive
            </Badge>
          ),
        size: 100,
        meta: { headerTitle: 'Active' },
      },
      {
        id: 'actions',
        header: () => <span className="sr-only">Actions</span>,
        cell: ({ row }) => (
          <div className="flex justify-end gap-1">
            <Button
              size="icon"
              variant="ghost"
              aria-label="Edit"
              onClick={(e) => {
                e.stopPropagation();
                setEditing(row.original);
              }}
            >
              <Pencil className="size-4" />
            </Button>
            <Button
              size="icon"
              variant="ghost"
              aria-label="Delete"
              onClick={(e) => {
                e.stopPropagation();
                setDeleteTarget(row.original);
              }}
            >
              <Trash2 className="size-4 text-destructive" />
            </Button>
          </div>
        ),
        size: 90,
        enableResizing: false,
        meta: { headerTitle: 'Actions' },
      },
    ],
    [],
  );

  if (isLoading) {
    return <Skeleton className="h-48 w-full" />;
  }
  if (error) {
    return (
      <Card>
        <CardContent className="pt-6 text-sm text-rose-600">
          Failed to load form SLA configurations: {(error as Error).message}
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-muted-foreground">
            Per-form SLA stage rules. Each row defines which form transition starts a
            tracker, marks it responded, and marks it resolved. Chain stages via the
            Next stage column for multi-step flows (e.g. stock inquiry: project sales →
            purchasing).
          </p>
        </div>
        <Button onClick={() => setCreating(true)}>
          <Plus className="mr-1 size-4" /> Add stage
        </Button>
      </div>

      {Array.from(grouped.entries()).length === 0 ? (
        <Card>
          <CardContent className="pt-6 text-sm text-muted-foreground">
            No SLA configurations yet. Click &quot;Add stage&quot; to attach an SLA to
            one of the four forms.
          </CardContent>
        </Card>
      ) : (
        Array.from(grouped.entries()).map(([type, rows]) => (
          <PanelDataGrid<FormSLAConfig>
            key={type}
            title={FORM_SLA_TYPE_LABELS[type] ?? type}
            columns={columns}
            rows={rows}
            getRowId={(row) => row.id}
            listingKey={`sla_management.form_sla_config.view::${type}`}
            emptyTitle="No stages"
          />
        ))
      )}

      <FormSLAConfigDialog
        open={creating || editing != null}
        existing={editing}
        configs={data || []}
        onClose={() => {
          setCreating(false);
          setEditing(null);
        }}
        onSaved={() => {
          queryClient.invalidateQueries({ queryKey });
          setCreating(false);
          setEditing(null);
        }}
      />

      <AlertDialog
        open={deleteTarget != null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Confirm delete</AlertDialogTitle>
            <AlertDialogDescription>
              Delete the {deleteTarget?.source_entity_type}/{deleteTarget?.stage_code}{' '}
              SLA stage configuration? Existing trackers are not affected. This action
              cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteMut.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={deleteMut.isPending}
              onClick={(e) => {
                e.preventDefault();
                if (deleteTarget) deleteMut.mutate(deleteTarget.id);
              }}
            >
              {deleteMut.isPending ? 'Deleting…' : 'Delete'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
