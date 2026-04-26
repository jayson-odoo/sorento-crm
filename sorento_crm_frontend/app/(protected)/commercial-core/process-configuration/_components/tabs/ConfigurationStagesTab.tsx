'use client';

import { CSSProperties, useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { GripVertical, Pencil, Plus, Trash2 } from 'lucide-react';
import {
  closestCenter,
  DndContext,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import { restrictToVerticalAxis } from '@dnd-kit/modifiers';
import { arrayMove, SortableContext, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { cn } from '@/lib/utils';
import {
  createWorkflowStage,
  deleteWorkflowStage,
  getWorkflowStages,
  updateWorkflowStage,
} from '../../services/workflowStageService';
import type {
  WorkflowDomain,
  WorkflowStageCreatePayload,
  WorkflowStageRow,
  WorkflowStageUpdatePayload,
} from '../../types/workflowStage.types';
import { CreateStageForm, EditStageForm } from '../../workflow-stages/workflowStageForms';

const STAGE_KINDS: { domain: WorkflowDomain; label: string }[] = [
  { domain: 'lead', label: 'Lead Stages' },
  { domain: 'order', label: 'Order Stages' },
  { domain: 'project', label: 'Project Stages' },
  { domain: 'task', label: 'Task Stages' },
  { domain: 'quotation', label: 'Quotation Stages' },
];

function SortableStageRow({
  row,
  order,
  onEdit,
  onDelete,
}: {
  row: WorkflowStageRow;
  order: number;
  onEdit: (row: WorkflowStageRow) => void;
  onDelete: (row: WorkflowStageRow) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: row.id });

  const style: CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.75 : 1,
  };

  return (
    // sorento TableRow does not forward `ref` through asChild — cast to bypass.
    <TableRow
      // @ts-expect-error: dnd-kit needs a ref on the tr; sorento TableRow types don't expose it.
      ref={setNodeRef}
      style={style}
      className="border-b border-[#e5e7eb]"
    >
      <TableCell className="w-[52px]">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="size-8 cursor-grab text-muted-foreground active:cursor-grabbing"
          aria-label={`Reorder stage ${row.label}`}
          {...attributes}
          {...listeners}
        >
          <GripVertical className="size-4" />
        </Button>
      </TableCell>
      <TableCell className="font-medium text-[#e7000b]">{row.code}</TableCell>
      <TableCell className="text-[#364153]">{row.label}</TableCell>
      <TableCell>
        <div className="inline-flex items-center gap-2">
          <span
            className="inline-block size-4 rounded-full border border-black/10"
            style={{ backgroundColor: row.color_hex || '#E7000B' }}
            aria-label="Stage color"
          />
          <span className="text-xs text-[#6a7282]">{row.color_hex || '#E7000B'}</span>
        </div>
      </TableCell>
      <TableCell>{order}</TableCell>
      <TableCell className="text-center">
        <FigCheck value={row.is_terminal} />
      </TableCell>
      <TableCell className="text-center">
        {row.domain === 'lead' ? <FigCheck value={row.allows_conversion === true} /> : <span className="text-muted-foreground text-base">−</span>}
      </TableCell>
      <TableCell className="text-center">
        <FigCheck value={row.can_go_back} />
      </TableCell>
      <TableCell className="text-center">
        <ActivePill active={row.is_active} />
      </TableCell>
      <TableCell className="text-center">
        {row.is_cancelled ? <span className="text-sm text-amber-800">Yes</span> : <span className="text-muted-foreground text-base">−</span>}
      </TableCell>
      <TableCell className="text-end">
        <Button variant="ghost" size="icon" type="button" aria-label="Edit" onClick={() => onEdit(row)}>
          <Pencil className="size-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          type="button"
          aria-label="Delete"
          className="text-destructive hover:text-destructive"
          onClick={() => onDelete(row)}
        >
          <Trash2 className="size-4" />
        </Button>
      </TableCell>
    </TableRow>
  );
}

function FigCheck({ value }: { value: boolean | null | undefined }) {
  if (value === true) {
    return (
      <span className="inline-flex size-5 items-center justify-center rounded-full bg-emerald-100">
        <span className="text-[12px] leading-none text-emerald-600">✓</span>
      </span>
    );
  }
  return <span className="text-muted-foreground text-base">−</span>;
}

function ActivePill({ active }: { active: boolean }) {
  if (!active) return <span className="text-muted-foreground text-sm">No</span>;
  return (
    <span className="inline-flex items-center rounded-full bg-emerald-100 px-2.5 py-0.5 text-[12px] font-medium text-emerald-900">
      Active
    </span>
  );
}

export function ConfigurationStagesTab() {
  const qc = useQueryClient();
  const [stageKind, setStageKind] = useState<WorkflowDomain>('lead');
  const [editing, setEditing] = useState<WorkflowStageRow | null>(null);
  const [creating, setCreating] = useState(false);
  const [orderedRows, setOrderedRows] = useState<WorkflowStageRow[]>([]);

  const { data: rows = [], isLoading } = useQuery({
    queryKey: ['workflow-stages', stageKind],
    queryFn: () =>
      getWorkflowStages({
        domain: stageKind,
        includeInactive: true,
      }),
    staleTime: 30_000,
  });

  const sorted = useMemo(
    () =>
      [...rows].sort((a, b) => a.sort_order - b.sort_order || a.code.localeCompare(b.code)),
    [rows],
  );

  // Sync orderedRows from server-sorted list only when the underlying ids/order
  // change — comparing references would loop forever because ``sorted`` returns
  // a new array every render after each setState.
  useEffect(() => {
    setOrderedRows((prev) => {
      if (prev.length !== sorted.length) return sorted;
      for (let i = 0; i < sorted.length; i++) {
        if (prev[i]?.id !== sorted[i].id) return sorted;
        if (prev[i]?.sort_order !== sorted[i].sort_order) return sorted;
        if (prev[i]?.updated_at !== sorted[i].updated_at) return sorted;
      }
      return prev;
    });
  }, [sorted]);

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

  const reorder = useMutation({
    mutationFn: async (nextRows: WorkflowStageRow[]) => {
      await Promise.all(
        nextRows.map((row, index) =>
          updateWorkflowStage(row.id, {
            sort_order: index,
          }),
        ),
      );
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['workflow-stages'] });
      toast.success('Stage order updated');
    },
    onError: (e: Error) => {
      toast.error(e.message);
      setOrderedRows(sorted);
    },
  });

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const oldIndex = orderedRows.findIndex((row) => row.id === active.id);
    const newIndex = orderedRows.findIndex((row) => row.id === over.id);
    if (oldIndex < 0 || newIndex < 0 || oldIndex === newIndex) return;

    const nextRows = arrayMove(orderedRows, oldIndex, newIndex);
    setOrderedRows(nextRows);
    reorder.mutate(nextRows);
  };

  return (
    <div className="overflow-hidden rounded-[10px] border border-[#e5e7eb] bg-white">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[#e5e7eb] px-6 py-6">
        <div className="flex flex-wrap gap-2">
          {STAGE_KINDS.map((s) => (
            <button
              key={s.domain}
              type="button"
              onClick={() => setStageKind(s.domain)}
              className={cn(
                'rounded-lg px-4 py-2 text-sm font-medium transition-colors',
                stageKind === s.domain
                  ? 'bg-[#155dfc] text-white shadow-sm'
                  : 'border border-black/10 bg-white text-[#0a0a0a] hover:bg-muted/40',
              )}
            >
              {s.label}
            </button>
          ))}
        </div>
        <Button
          type="button"
          size="sm"
          variant="destructive"
          className="rounded-lg bg-[#e7000b] hover:bg-[#c90009]"
          onClick={() => setCreating(true)}
        >
          <Plus className="size-4" />
          Add Stage
        </Button>
      </div>

      <div className="overflow-x-auto">
        {isLoading ? (
          <div className="p-6">
            <Skeleton className="h-48 w-full" />
          </div>
        ) : (
          <DndContext sensors={sensors} collisionDetection={closestCenter} modifiers={[restrictToVerticalAxis]} onDragEnd={handleDragEnd}>
            <Table>
              <TableHeader>
                <TableRow className="border-b bg-[#f9fafb] hover:bg-[#f9fafb]">
                  <TableHead className="w-[52px]" />
                  <TableHead className="font-medium text-[#364153]">Code</TableHead>
                  <TableHead className="font-medium text-[#364153]">Label</TableHead>
                  <TableHead className="font-medium text-[#364153]">Color</TableHead>
                  <TableHead className="font-medium text-[#364153]">Order</TableHead>
                  <TableHead className="text-center font-medium text-[#364153]">Terminal</TableHead>
                  <TableHead className="text-center font-medium text-[#364153]">Allows Conversion</TableHead>
                  <TableHead className="text-center font-medium text-[#364153]">Can Go Back</TableHead>
                  <TableHead className="text-center font-medium text-[#364153]">Active</TableHead>
                  <TableHead className="text-center font-medium text-[#364153]">Cancelled</TableHead>
                  <TableHead className="text-end font-medium text-[#364153]">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <SortableContext items={orderedRows.map((row) => row.id)} strategy={verticalListSortingStrategy}>
                  {orderedRows.map((row, idx) => (
                    <SortableStageRow
                      key={row.id}
                      row={row}
                      order={idx}
                      onEdit={setEditing}
                      onDelete={(target) => {
                        if (confirm(`Delete stage ${target.domain}/${target.code}?`)) del.mutate(target.id);
                      }}
                    />
                  ))}
                </SortableContext>
              </TableBody>
            </Table>
          </DndContext>
        )}
      </div>

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
          <CreateStageForm
            lockDomain={stageKind}
            submitting={createMut.isPending}
            onSubmit={(data) => createMut.mutate(data)}
          />
        </DialogContent>
      </Dialog>
    </div>
  );
}
