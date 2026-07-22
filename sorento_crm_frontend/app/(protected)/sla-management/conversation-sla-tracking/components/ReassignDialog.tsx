'use client';

import { useEffect, useState } from 'react';
import { LoaderCircleIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { useVisibleUsers } from '../hooks/useTeamPendingSLA';
import type { VisibleUser } from '../services/conversationSLATrackingService';

function displayUser(u: VisibleUser): string {
  return u.name || u.email;
}

export interface ReassignDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Human-readable subject line, e.g. "Complaint · CMP-0001". Never a UUID. */
  taskLabel?: string | null;
  submitting?: boolean;
  /** Called with the chosen user's id. */
  onConfirm: (userId: string) => void;
}

/**
 * Shared reassign picker. User list is scope-B (visible-users endpoint) — only
 * colleagues the actor can see. Names only, no UUIDs.
 */
export default function ReassignDialog({
  open,
  onOpenChange,
  taskLabel,
  submitting = false,
  onConfirm,
}: ReassignDialogProps) {
  const { data: users = [], isLoading, error } = useVisibleUsers(open);
  const [selectedId, setSelectedId] = useState<string>('');

  useEffect(() => {
    if (!open) {
      setSelectedId('');
    }
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Reassign task</DialogTitle>
          <DialogDescription>
            {taskLabel ? `Hand off ${taskLabel} to a colleague.` : 'Hand off this task to a colleague.'}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2 py-1">
          <Label>Assign to</Label>
          <SearchableSelect
            value={selectedId}
            onChange={setSelectedId}
            options={users.map((u) => ({
              value: u.id,
              label: displayUser(u),
              searchText: `${u.name ?? ''} ${u.email}`.trim(),
            }))}
            placeholder={isLoading ? 'Loading users…' : 'Select a colleague'}
            emptyMessage="No colleagues available."
            disabled={isLoading || submitting}
            triggerClassName="w-full"
          />
          {error ? (
            <p className="text-xs text-destructive">{(error as Error).message}</p>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={() => selectedId && onConfirm(selectedId)} disabled={!selectedId || submitting}>
            {submitting && <LoaderCircleIcon className="animate-spin me-2 size-4" />}
            Reassign
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
