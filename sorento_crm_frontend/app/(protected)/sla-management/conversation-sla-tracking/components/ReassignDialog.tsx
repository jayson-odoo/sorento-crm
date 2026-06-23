'use client';

import { useEffect, useState } from 'react';
import { Check, ChevronsUpDown, LoaderCircleIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';
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
  const [pickerOpen, setPickerOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<string>('');

  useEffect(() => {
    if (!open) {
      setSelectedId('');
      setPickerOpen(false);
    }
  }, [open]);

  const selected = users.find((u) => u.id === selectedId);

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
          <Popover open={pickerOpen} onOpenChange={setPickerOpen}>
            <PopoverTrigger asChild>
              <Button
                variant="outline"
                role="combobox"
                aria-expanded={pickerOpen}
                className="w-full justify-between font-normal"
                disabled={isLoading || submitting}
              >
                {selected ? displayUser(selected) : isLoading ? 'Loading users…' : 'Select a colleague'}
                <ChevronsUpDown className="ms-2 size-4 shrink-0 opacity-50" />
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
              <Command>
                <CommandInput placeholder="Search by name or email..." />
                <CommandList>
                  <CommandEmpty>No colleagues available.</CommandEmpty>
                  <CommandGroup>
                    {users.map((u) => (
                      <CommandItem
                        key={u.id}
                        value={`${u.name ?? ''} ${u.email}`.trim()}
                        onSelect={() => {
                          setSelectedId(u.id);
                          setPickerOpen(false);
                        }}
                      >
                        <Check
                          className={cn(
                            'me-2 size-4',
                            selectedId === u.id ? 'opacity-100' : 'opacity-0',
                          )}
                        />
                        {displayUser(u)}
                      </CommandItem>
                    ))}
                  </CommandGroup>
                </CommandList>
              </Command>
            </PopoverContent>
          </Popover>
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
