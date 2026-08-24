'use client';

import { useState } from 'react';
import { Check, LoaderCircleIcon, Pencil, Trash2, UserRoundPlus, X } from 'lucide-react';
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
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { useVisibleUsers } from '@/app/(protected)/sla-management/conversation-sla-tracking/hooks/useTeamPendingSLA';
import {
  useMyCoverage,
  useSubscribeCoverage,
  useUnsubscribeCoverage,
  useUpdateCoverage,
} from '../hooks/useCoverage';
import type { CoverageSub } from '../services/coverageService';

/** `expires_at` is a DATE (coverage end day), not a timezone-bearing instant. Take the
 *  yyyy-mm-dd calendar prefix directly - never round-trip through `new Date(...)`, which
 *  parses a naive backend timestamp as local then shifts it to UTC (−1 day in UTC+8). */
function dateOnly(iso: string | null): string {
  if (!iso) return '';
  const m = /^(\d{4}-\d{2}-\d{2})/.exec(iso);
  return m ? m[1] : '';
}

function formatDate(iso: string | null): string {
  const d = dateOnly(iso);
  if (!d) return '';
  const [y, mo, day] = d.split('-');
  return `${day}/${mo}/${y}`; // dd/mm/yyyy, tz-safe
}

/** ISO timestamp → yyyy-mm-dd for a native <input type="date"> (tz-safe). */
function toDateInput(iso: string | null): string {
  return dateOnly(iso);
}

export function CoverageSection() {
  const { data: coverage = [], isLoading, error } = useMyCoverage();
  const { data: visibleUsers = [], isLoading: usersLoading } = useVisibleUsers();
  const subscribe = useSubscribeCoverage();
  const update = useUpdateCoverage();
  const unsubscribe = useUnsubscribeCoverage();

  const [selectedId, setSelectedId] = useState('');
  const [expiresAt, setExpiresAt] = useState('');
  // Default ON: auto-assign is the primary ask. Off = notify-only.
  const [redirect, setRedirect] = useState(true);
  const [removeTarget, setRemoveTarget] = useState<CoverageSub | null>(null);
  const [editId, setEditId] = useState('');
  const [editDate, setEditDate] = useState('');
  const [editRedirect, setEditRedirect] = useState(true);

  // Don't offer colleagues I'm already covering.
  const covered = new Set(coverage.map((c) => c.target_user_id));
  const selectable = visibleUsers.filter((u) => !covered.has(u.id));

  const handleAdd = () => {
    if (!selectedId) return;
    subscribe.mutate(
      {
        targetUserId: selectedId,
        expiresAt: expiresAt ? new Date(expiresAt).toISOString() : undefined,
        redirectAssignments: redirect,
      },
      {
        onSuccess: () => {
          setSelectedId('');
          setExpiresAt('');
          setRedirect(true);
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
    setEditRedirect(c.redirect_assignments);
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
        redirectAssignments: editRedirect,
      },
      { onSuccess: () => cancelEdit() },
    );
  };

  return (
    <Card>
      <CardHeader className="gap-1">
        <CardTitle>Coverage</CardTitle>
        <p className="text-sm text-muted-foreground">
          Auto-assign: their SLA tasks (assignment &amp; escalation) are reassigned to you.
          Notify only: you&apos;re notified and can take over manually.
        </p>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Add control */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="flex-1 space-y-1.5">
            <Label>Cover for</Label>
            <SearchableSelect
              value={selectedId}
              onChange={setSelectedId}
              options={selectable.map((u) => ({
                value: u.id,
                label: u.name || u.email,
                // Search both name and email - the old picker matched on both.
                searchText: `${u.name ?? ''} ${u.email}`.trim(),
              }))}
              placeholder="Select a colleague"
              emptyMessage="No colleagues available."
              disabled={usersLoading || subscribe.isPending}
              triggerClassName="w-full"
            />
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
          <div className="space-y-1.5">
            <Label htmlFor="coverage-redirect">Auto-assign their tasks to me</Label>
            <div className="flex h-9 items-center gap-2">
              <Switch
                id="coverage-redirect"
                checked={redirect}
                onCheckedChange={setRedirect}
                disabled={subscribe.isPending}
              />
              <span className="text-xs text-muted-foreground">
                {redirect ? 'Auto-assign' : 'Notify only'}
              </span>
            </div>
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

        {/* Coverage list - always rendered with an explicit empty state */}
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
              Pick a colleague above to hold their incoming SLA tasks while they&apos;re away.
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
                    <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                      {c.is_active ? (
                        <Badge variant="success" appearance="ghost">Active</Badge>
                      ) : (
                        <Badge variant="secondary" appearance="ghost">Inactive</Badge>
                      )}
                      {editing ? (
                        <span className="flex items-center gap-1.5">
                          <Switch
                            checked={editRedirect}
                            onCheckedChange={setEditRedirect}
                            disabled={savingThis}
                            aria-label={`Auto-assign tasks for ${c.target_user_name}`}
                          />
                          <span>{editRedirect ? 'Auto-assign' : 'Notify only'}</span>
                        </span>
                      ) : c.redirect_assignments ? (
                        <Badge variant="primary" appearance="ghost">Auto-assign</Badge>
                      ) : (
                        <Badge variant="secondary" appearance="ghost">Notify only</Badge>
                      )}
                      {c.assigned_by_hod && (
                        <Badge variant="warning" appearance="ghost">
                          Assigned by {c.assigned_by_name ?? 'manager'}
                        </Badge>
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
