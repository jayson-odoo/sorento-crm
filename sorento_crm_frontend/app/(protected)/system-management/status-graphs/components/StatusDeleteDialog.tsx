'use client';

import { useState } from 'react';
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
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useDeleteStatus, useMigrateStatusRecords } from '../hooks/useStatusGraphs';
import type { Status } from '../types/statusGraph.types';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  entityType: string;
  scopeId: string | null;
  status: Status;
  /** Every other status in the same graph, as migration targets. */
  siblings: Status[];
}

/**
 * Delete, with the blocked case handled up front rather than as an error.
 *
 * A status that still has records cannot be deleted (the server refuses). Telling
 * the user that only after they click is a dead end, so when the count is non-zero
 * this dialog turns into "move these records first" and offers the target picker.
 */
export default function StatusDeleteDialog({
  open,
  onOpenChange,
  entityType,
  scopeId,
  status,
  siblings,
}: Props) {
  const [target, setTarget] = useState('');
  const deleteMutation = useDeleteStatus(entityType, scopeId);
  const migrateMutation = useMigrateStatusRecords(entityType, scopeId);

  const inUse = (status.record_count ?? 0) > 0;
  const busy = deleteMutation.isPending || migrateMutation.isPending;

  const close = () => {
    setTarget('');
    onOpenChange(false);
  };

  const handleDelete = () => deleteMutation.mutate(status.id, { onSuccess: close });
  const handleMigrate = () =>
    migrateMutation.mutate({ id: status.id, toStatusId: target }, { onSuccess: () => setTarget('') });

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? onOpenChange(true) : close())}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{inUse ? 'Move records first' : 'Confirm delete'}</DialogTitle>
        </DialogHeader>

        {inUse ? (
          <>
            <DialogDescription>
              <strong className="text-foreground">{status.label}</strong> is still used by{' '}
              {status.record_count} record{status.record_count === 1 ? '' : 's'}, so it cannot be
              deleted yet. Choose where those records should go.
            </DialogDescription>
            <div className="grid gap-2">
              <Label>Move records to</Label>
              <SearchableSelect
                value={target}
                onChange={setTarget}
                options={siblings.map((s) => ({ value: s.id, label: s.label }))}
                placeholder="Pick a status"
                triggerClassName="w-full"
              />
              {siblings.length === 0 && (
                <p className="text-xs text-muted-foreground">
                  There is no other status to move them into. Add one first.
                </p>
              )}
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={close}>
                Cancel
              </Button>
              <Button type="button" disabled={!target || busy} onClick={handleMigrate}>
                {migrateMutation.isPending && (
                  <LoaderCircleIcon className="size-4 animate-spin" />
                )}
                Move records
              </Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <DialogDescription>
              Delete the status <strong className="text-foreground">{status.label}</strong>? Any
              transitions into or out of it are removed too. This action cannot be undone.
            </DialogDescription>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={close}>
                Cancel
              </Button>
              <Button
                type="button"
                disabled={busy}
                onClick={handleDelete}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                {deleteMutation.isPending && <LoaderCircleIcon className="size-4 animate-spin" />}
                Delete
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
