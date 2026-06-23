'use client';

import { useState } from 'react';
import { ChevronsUpDown, Check, LoaderCircleIcon, Pencil, Trash2, UserRoundPlus, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
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
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { useVisibleUsers } from '@/app/(protected)/sla-management/conversation-sla-tracking/hooks/useTeamPendingSLA';
import {
  useMyCoverage,
  useSubscribeCoverage,
  useUnsubscribeCoverage,
  useUpdateCoverage,
} from '../hooks/useCoverage';
import type { CoverageSub } from '../services/coverageService';

function formatDate(iso: string | null): string {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString();
}

/** ISO timestamp → yyyy-mm-dd for a native <input type="date">. */
function toDateInput(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toISOString().slice(0, 10);
}

export function CoverageSection() {
  const { data: coverage = [], isLoading, error } = useMyCoverage();
  const { data: visibleUsers = [], isLoading: usersLoading } = useVisibleUsers();
  const subscribe = useSubscribeCoverage();
  const update = useUpdateCoverage();
  const unsubscribe = useUnsubscribeCoverage();

  const [pickerOpen, setPickerOpen] = useState(false);
  const [selectedId, setSelectedId] = useState('');
  const [expiresAt, setExpiresAt] = useState('');
  const [removeTarget, setRemoveTarget] = useState<CoverageSub | null>(null);
  const [editId, setEditId] = useState('');
  const [editDate, setEditDate] = useState('');

  // Don't offer colleagues I'm already covering.
  const covered = new Set(coverage.map((c) => c.target_user_id));
  const selectable = visibleUsers.filter((u) => !covered.has(u.id));
  const selected = visibleUsers.find((u) => u.id === selectedId);

  const handleAdd = () => {
    if (!selectedId) return;
    subscribe.mutate(
      { targetUserId: selectedId, expiresAt: expiresAt ? new Date(expiresAt).toISOString() : undefined },
      {
        onSuccess: () => {
          setSelectedId('');
          setExpiresAt('');
        },
      },
    );
  };

  const handleRemove = () => {
    if (!removeTarget) return;
    unsubscribe.mutate(removeTarget.target_user_id, {
      onSuccess: () => setRemoveTarget(null),
    });
  };

  const startEdit = (c: CoverageSub) => {
    setEditId(c.target_user_id);
    setEditDate(toDateInput(c.expires_at));
  };

  const cancelEdit = () => {
    setEditId('');
    setEditDate('');
  };

  const handleSaveEdit = (c: CoverageSub) => {
    update.mutate(
      {
        targetUserId: c.target_user_id,
        expiresAt: editDate ? new Date(editDate).toISOString() : undefined,
      },
      { onSuccess: () => cancelEdit() },
    );
  };

  return (
    <Card>
      <CardHeader className="gap-1">
        <CardTitle>Coverage</CardTitle>
        <p className="text-sm text-muted-foreground">
          Get notified about a colleague&apos;s SLA assignments while you cover for them.
        </p>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Add control */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="flex-1 space-y-1.5">
            <Label>Cover for</Label>
            <Popover open={pickerOpen} onOpenChange={setPickerOpen}>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  role="combobox"
                  aria-expanded={pickerOpen}
                  className="w-full justify-between font-normal"
                  disabled={usersLoading || subscribe.isPending}
                >
                  {selected ? selected.name || selected.email : 'Select a colleague'}
                  <ChevronsUpDown className="ms-2 size-4 shrink-0 opacity-50" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
                <Command>
                  <CommandInput placeholder="Search by name or email..." />
                  <CommandList>
                    <CommandEmpty>No colleagues available.</CommandEmpty>
                    <CommandGroup>
                      {selectable.map((u) => (
                        <CommandItem
                          key={u.id}
                          value={`${u.name ?? ''} ${u.email}`.trim()}
                          onSelect={() => {
                            setSelectedId(u.id);
                            setPickerOpen(false);
                          }}
                        >
                          <Check
                            className={cn('me-2 size-4', selectedId === u.id ? 'opacity-100' : 'opacity-0')}
                          />
                          {u.name || u.email}
                        </CommandItem>
                      ))}
                    </CommandGroup>
                  </CommandList>
                </Command>
              </PopoverContent>
            </Popover>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="coverage-expires">Until (optional)</Label>
            <Input
              id="coverage-expires"
              type="date"
              value={expiresAt}
              onChange={(e) => setExpiresAt(e.target.value)}
              className="w-full sm:w-44"
            />
          </div>
          <Button onClick={handleAdd} disabled={!selectedId || subscribe.isPending}>
            {subscribe.isPending ? (
              <LoaderCircleIcon className="animate-spin me-2 size-4" />
            ) : (
              <UserRoundPlus className="me-2 size-4" />
            )}
            Add
          </Button>
        </div>

        {/* Coverage list — always rendered with an explicit empty state */}
        {error ? (
          <p className="text-sm text-destructive">{(error as Error).message}</p>
        ) : isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : coverage.length === 0 ? (
          <div className="rounded-md border border-dashed px-4 py-8 text-center">
            <p className="text-sm text-muted-foreground">
              You&apos;re not covering for anyone yet.
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              Pick a colleague above to receive their SLA assignment and escalation alerts.
            </p>
          </div>
        ) : (
          <ul className="divide-y rounded-md border">
            {coverage.map((c) => {
              const editing = editId === c.target_user_id;
              const savingThis = update.isPending && editing;
              return (
                <li key={c.id} className="flex items-center justify-between gap-3 px-4 py-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium" title={c.target_user_name ?? ''}>
                      {c.target_user_name}
                    </p>
                    <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
                      {c.is_active ? (
                        <Badge variant="success" appearance="ghost">Active</Badge>
                      ) : (
                        <Badge variant="secondary" appearance="ghost">Inactive</Badge>
                      )}
                      {editing ? (
                        <span className="flex items-center gap-2">
                          <span>Until</span>
                          <Input
                            type="date"
                            value={editDate}
                            onChange={(e) => setEditDate(e.target.value)}
                            disabled={savingThis}
                            className="h-8 w-40"
                            aria-label={`Coverage end date for ${c.target_user_name}`}
                          />
                          {editDate ? null : (
                            <span className="text-muted-foreground">(no end date)</span>
                          )}
                        </span>
                      ) : c.expires_at ? (
                        <span>Until {formatDate(c.expires_at)}</span>
                      ) : (
                        <span>No end date</span>
                      )}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    {editing ? (
                      <>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleSaveEdit(c)}
                          disabled={savingThis}
                          aria-label={`Save coverage end date for ${c.target_user_name}`}
                        >
                          {savingThis ? (
                            <LoaderCircleIcon className="size-4 animate-spin" />
                          ) : (
                            <Check className="size-4" />
                          )}
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={cancelEdit}
                          disabled={savingThis}
                          aria-label="Cancel editing"
                        >
                          <X className="size-4" />
                        </Button>
                      </>
                    ) : (
                      <>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => startEdit(c)}
                          disabled={update.isPending || unsubscribe.isPending}
                          aria-label={`Edit coverage end date for ${c.target_user_name}`}
                        >
                          <Pencil className="size-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="text-destructive hover:text-destructive"
                          onClick={() => setRemoveTarget(c)}
                          disabled={unsubscribe.isPending}
                          aria-label={`Stop covering for ${c.target_user_name}`}
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>

      <AlertDialog open={!!removeTarget} onOpenChange={(o) => !o && setRemoveTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Confirm delete</AlertDialogTitle>
            <AlertDialogDescription>
              Stop covering for {removeTarget?.target_user_name}? You will no longer receive their SLA
              alerts. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={unsubscribe.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={(e) => {
                e.preventDefault();
                handleRemove();
              }}
              disabled={unsubscribe.isPending}
            >
              {unsubscribe.isPending ? 'Removing…' : 'Remove'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
