'use client';

import { useEffect, useMemo, useState } from 'react';
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
import { Switch } from '@/components/ui/switch';
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
 * Shared reassign picker (the widget, the ticket drawer - never a fork).
 *
 * User list is scope-B (visible-users endpoint) - only colleagues the actor can
 * see. Names only, no UUIDs.
 *
 * AC-N7: each colleague says whether they are Respond-linked, and the list can
 * be filtered to those, because a reply from an unlinked user cannot carry a
 * real Respond sender identity. The linkage rides on the picker's OWN rows
 * (`respond_linked` on visible-users) - it used to come from the shared
 * user-select endpoint, which is gated by `user_management.users.view` and so
 * degraded to no-badge-no-filter for exactly the SLA agents who need it.
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
  const [linkedOnly, setLinkedOnly] = useState(false);

  useEffect(() => {
    if (!open) {
      setSelectedId('');
      setLinkedOnly(false);
    }
  }, [open]);

  const options = useMemo(() => {
    const visible = linkedOnly ? users.filter((u) => u.respond_linked) : users;
    return visible.map((u) => ({
      value: u.id,
      label: displayUser(u),
      searchText: `${u.name ?? ''} ${u.email}`.trim(),
      // Carried on the option so `renderOption` can badge it without a lookup.
      description: u.respond_linked ? 'Respond-linked' : undefined,
    }));
  }, [users, linkedOnly]);

  // A filter that hides the selection would submit someone the user can no
  // longer see. Drop the selection instead of carrying it invisibly.
  useEffect(() => {
    if (selectedId && !options.some((o) => o.value === selectedId)) setSelectedId('');
  }, [options, selectedId]);

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
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Label htmlFor="reassign-assignee">Assign to</Label>
            <div className="flex items-center gap-2">
              <Switch
                id="reassign-respond-linked-only"
                data-testid="reassign-respond-linked-filter"
                size="sm"
                checked={linkedOnly}
                onCheckedChange={(next) => setLinkedOnly(!!next)}
                disabled={submitting}
              />
              <Label
                htmlFor="reassign-respond-linked-only"
                className="text-xs font-normal text-muted-foreground"
              >
                Respond-linked only
              </Label>
            </div>
          </div>
          <SearchableSelect
            id="reassign-assignee"
            value={selectedId}
            onChange={setSelectedId}
            options={options}
            renderOption={(opt) => (
              <span className="flex min-w-0 items-center gap-2">
                <span className="truncate">{opt.label}</span>
                {opt.description === 'Respond-linked' && (
                  <span
                    data-testid={`respond-linked-badge-${opt.value}`}
                    className="shrink-0 rounded-full bg-emerald-100 px-1.5 py-0.5 text-[10px] font-medium text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-200"
                  >
                    Respond-linked
                  </span>
                )}
              </span>
            )}
            placeholder={isLoading ? 'Loading users…' : 'Select a colleague'}
            emptyMessage={
              linkedOnly ? 'No Respond-linked colleagues.' : 'No colleagues available.'
            }
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
