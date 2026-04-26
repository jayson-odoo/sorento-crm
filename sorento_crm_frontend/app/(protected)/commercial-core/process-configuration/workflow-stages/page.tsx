'use client';

import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Pencil, Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  createWorkflowStage,
  deleteWorkflowStage,
  getWorkflowStages,
  updateWorkflowStage,
} from '../services/workflowStageService';
import type { WorkflowStageCreatePayload, WorkflowStageRow, WorkflowStageUpdatePayload } from '../types/workflowStage.types';
import { ADMIN_DOMAINS, CreateStageForm, EditStageForm } from './workflowStageForms';

function boolCell(v: boolean | null | undefined, na?: boolean) {
  if (na && (v === null || v === undefined)) return '—';
  return v ? 'Yes' : 'No';
}

export default function WorkflowStagesAdminPage() {
  const qc = useQueryClient();
  const [domainFilter, setDomainFilter] = useState<string>('all');
  const [editing, setEditing] = useState<WorkflowStageRow | null>(null);
  const [creating, setCreating] = useState(false);

  const { data: rows = [], isLoading } = useQuery({
    queryKey: ['workflow-stages', domainFilter],
    queryFn: () =>
      getWorkflowStages({
        domain: domainFilter === 'all' ? undefined : domainFilter,
        includeInactive: true,
      }),
    staleTime: 30_000,
  });

  const sorted = useMemo(
    () =>
      [...rows].sort(
        (a, b) => a.domain.localeCompare(b.domain) || a.sort_order - b.sort_order || a.code.localeCompare(b.code),
      ),
    [rows],
  );

  const patch = useMutation({
    mutationFn: ({ id, data }: { id: string; data: WorkflowStageUpdatePayload }) => updateWorkflowStage(id, data),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['workflow-stages'] });
      toast.success('Stage saved');
      setEditing(null);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const createMut = useMutation({
    mutationFn: (data: WorkflowStageCreatePayload) => createWorkflowStage(data),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['workflow-stages'] });
      toast.success('Stage created');
      setCreating(false);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const del = useMutation({
    mutationFn: (id: string) => deleteWorkflowStage(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['workflow-stages'] });
      toast.success('Stage deleted');
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
        <CardTitle>Workflow stages</CardTitle>
        <div className="flex flex-wrap items-center gap-2">
          <Select value={domainFilter} onValueChange={setDomainFilter}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="Domain" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All domains</SelectItem>
              {ADMIN_DOMAINS.map((d) => (
                <SelectItem key={d.value} value={d.value}>
                  {d.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button size="sm" type="button" onClick={() => setCreating(true)}>
            <Plus className="size-4" />
            Add
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Domain</TableHead>
                  <TableHead>Code</TableHead>
                  <TableHead>Label</TableHead>
                  <TableHead>Color</TableHead>
                  <TableHead>Order</TableHead>
                  <TableHead>Terminal</TableHead>
                  <TableHead>Allows conversion</TableHead>
                  <TableHead>Can go back</TableHead>
                  <TableHead>Active</TableHead>
                  <TableHead>Cancelled</TableHead>
                  <TableHead className="text-end">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sorted.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell className="font-medium capitalize">{row.domain}</TableCell>
                    <TableCell>{row.code}</TableCell>
                    <TableCell>{row.label}</TableCell>
                    <TableCell>
                      <div className="inline-flex items-center gap-2">
                        <span
                          className="inline-block size-4 rounded-full border border-black/10"
                          style={{ backgroundColor: row.color_hex || '#E7000B' }}
                          aria-label="Stage color"
                        />
                        <span className="text-xs text-muted-foreground">{row.color_hex || '#E7000B'}</span>
                      </div>
                    </TableCell>
                    <TableCell>{row.sort_order}</TableCell>
                    <TableCell>{boolCell(row.is_terminal)}</TableCell>
                    <TableCell>{boolCell(row.allows_conversion ?? false, true)}</TableCell>
                    <TableCell>{boolCell(row.can_go_back)}</TableCell>
                    <TableCell>{boolCell(row.is_active)}</TableCell>
                    <TableCell>{boolCell(row.is_cancelled)}</TableCell>
                    <TableCell className="text-end">
                      <Button variant="ghost" size="icon" type="button" aria-label="Edit" onClick={() => setEditing(row)}>
                        <Pencil className="size-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        type="button"
                        aria-label="Delete"
                        className="text-destructive hover:text-destructive"
                        onClick={() => {
                          if (confirm(`Delete stage ${row.domain}/${row.code}?`)) del.mutate(row.id);
                        }}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>

      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Edit workflow stage</DialogTitle>
          </DialogHeader>
          {editing ? (
            <EditStageForm
              row={editing}
              submitting={patch.isPending}
              onSubmit={(data) => patch.mutate({ id: editing.id, data })}
            />
          ) : null}
        </DialogContent>
      </Dialog>

      <Dialog open={creating} onOpenChange={(o) => !o && setCreating(false)}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>New workflow stage</DialogTitle>
          </DialogHeader>
          <CreateStageForm submitting={createMut.isPending} onSubmit={(data) => createMut.mutate(data)} />
        </DialogContent>
      </Dialog>
    </Card>
  );
}
