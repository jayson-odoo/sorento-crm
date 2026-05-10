'use client';

import { useMemo, useState } from 'react';
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import { Plus, Pencil, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
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
import { toast } from 'sonner';
import {
  listFormSLAConfigs,
  deleteFormSLAConfig,
  FORM_SLA_TYPE_LABELS,
  type FormSLAConfig,
  type FormSLASourceType,
} from '../../_shared/formSLAService';
import FormSLAConfigDialog from './FormSLAConfigDialog';

function EventChips({ value }: { value: string | null | undefined }) {
  if (!value) return <>—</>;
  const events = value.split(',').map((s) => s.trim()).filter(Boolean);
  if (events.length === 0) return <>—</>;
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
          <h1 className="text-2xl font-bold">Form SLA Configuration</h1>
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
          <Card key={type}>
            <CardContent className="space-y-2 pt-6">
              <div className="text-base font-semibold">
                {FORM_SLA_TYPE_LABELS[type] ?? type}
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Stage</TableHead>
                    <TableHead>Policy</TableHead>
                    <TableHead>Agent</TableHead>
                    <TableHead>Team set</TableHead>
                    <TableHead>Start</TableHead>
                    <TableHead>Respond</TableHead>
                    <TableHead>Resolve</TableHead>
                    <TableHead>Next stage</TableHead>
                    <TableHead>Active</TableHead>
                    <TableHead className="w-24 text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((c) => (
                    <TableRow key={c.id}>
                      <TableCell className="font-medium">{c.stage_code}</TableCell>
                      <TableCell title={c.policy_id}>
                        {c.policy_name || c.policy_code || c.policy_id.slice(0, 8)}
                      </TableCell>
                      <TableCell>{c.agent_code}</TableCell>
                      <TableCell>{c.team_set_code || '—'}</TableCell>
                      <TableCell>
                        <code className="rounded bg-muted px-1.5 py-0.5 text-xs">
                          {c.start_event}
                        </code>
                      </TableCell>
                      <TableCell>
                        <EventChips value={c.respond_event} />
                      </TableCell>
                      <TableCell>
                        <EventChips value={c.resolve_event} />
                      </TableCell>
                      <TableCell>
                        {c.next_stage_code ? (
                          <Badge variant="outline">{c.next_stage_code}</Badge>
                        ) : (
                          '—'
                        )}
                      </TableCell>
                      <TableCell>
                        {c.is_active ? (
                          <Badge variant="outline" className="border-emerald-300 text-emerald-700">
                            Active
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="border-slate-300 text-slate-500">
                            Inactive
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          size="icon"
                          variant="ghost"
                          aria-label="Edit"
                          onClick={() => setEditing(c)}
                        >
                          <Pencil className="size-4" />
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          aria-label="Delete"
                          onClick={() => setDeleteTarget(c)}
                        >
                          <Trash2 className="size-4 text-destructive" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
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
