'use client';

import { LoaderCircleIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useDeleteTransition } from '../hooks/useStatusGraphs';
import type { StatusTransition } from '../types/statusGraph.types';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  entityType: string;
  scopeId: string | null;
  transition: StatusTransition;
  fromLabel: string;
  toLabel: string;
}

export default function TransitionDeleteDialog({
  open,
  onOpenChange,
  entityType,
  scopeId,
  transition,
  fromLabel,
  toLabel,
}: Props) {
  const deleteMutation = useDeleteTransition(entityType, scopeId);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Confirm delete</DialogTitle>
        </DialogHeader>
        <DialogDescription>
          Delete the transition <strong className="text-foreground">{transition.label}</strong>?
          Records will no longer be able to move from{' '}
          <strong className="text-foreground">{fromLabel}</strong> to{' '}
          <strong className="text-foreground">{toLabel}</strong>. This action cannot be undone.
        </DialogDescription>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            disabled={deleteMutation.isPending}
            onClick={() =>
              deleteMutation.mutate(transition.id, { onSuccess: () => onOpenChange(false) })
            }
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {deleteMutation.isPending && <LoaderCircleIcon className="size-4 animate-spin" />}
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
