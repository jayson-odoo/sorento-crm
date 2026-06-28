'use client';

import { useMemo, useState } from 'react';
import { useSession } from 'next-auth/react';
import {
  ArrowRight,
  Check,
  ChevronsUpDown,
  LoaderCircleIcon,
  Pencil,
  Trash2,
  UserRoundPlus,
  X,
} from 'lucide-react';
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
import { Switch } from '@/components/ui/switch';
import { cn } from '@/lib/utils';
import { useVisibleUsers } from '@/app/(protected)/sla-management/conversation-sla-tracking/hooks/useTeamPendingSLA';
import {
  useAssignCoverage,
  useMyCoverage,
  useRevokeCoverageById,
  useSubscribeCoverage,
  useTeamCoverage,
  useUnsubscribeCoverage,
  useUpdateCoverage,
} from '../hooks/useCoverage';

/** tz-safe yyyy-mm-dd → dd/mm/yyyy (never round-trip through Date; see coverage-section). */
function formatDate(iso: string | null): string {
  if (!iso) return '';
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : '';
}
function toDateInput(iso: string | null): string {
  if (!iso) return '';
  const m = /^(\d{4}-\d{2}-\d{2})/.exec(iso);
  return m ? m[1] : '';
}

const ME = '__me__';

/** One normalized coverage row across the self-service and team sources. */
interface Row {
  id: string;
  covererId: string;
  covererName: string;
  isMeCoverer: boolean;
  coveredId: string;
  coveredName: string;
  redirect: boolean;
  expiresAt: string | null;
  /** assigned = a manager set this up (created_by != coverer); self = the coverer set it. */
  assignedByName: string | null;
  source: 'mine' | 'team';
}

interface PickerProps {
  value: string;
  onChange: (id: string) => void;
  options: { id: string; label: string }[];
  placeholder: string;
  disabled?: boolean;
}

function Picker({ value, onChange, options, placeholder, disabled }: PickerProps) {
  const [open, setOpen] = useState(false);
  const selected = options.find((o) => o.id === value);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="w-full justify-between font-normal"
          disabled={disabled}
        >
          {selected ? selected.label : placeholder}
          <ChevronsUpDown className="ms-2 size-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
        <Command>
          <CommandInput placeholder="Search by name or email..." />
          <CommandList>
            <CommandEmpty>No colleagues available.</CommandEmpty>
            <CommandGroup>
              {options.map((o) => (
                <CommandItem
                  key={o.id}
                  value={o.label}
                  onSelect={() => {
                    onChange(o.id);
                    setOpen(false);
                  }}
                >
                  <Check className={cn('me-2 size-4', value === o.id ? 'opacity-100' : 'opacity-0')} />
                  {o.label}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

/** Unified coverage manager. ONE form: pick who covers whom (the coverer defaults to
 * "You"; managers with `canManageTeam` can pick someone else). ONE list of
 * "coverer → covered" rows. The self-vs-team split is hidden behind a single mental
 * model. Non-managers can only set themselves as the coverer. */
export function CoverageManager({ canManageTeam }: { canManageTeam: boolean }) {
  const { data: session } = useSession();
  const myId = session?.user?.id ?? null;
  const { data: visibleUsers = [], isLoading: usersLoading } = useVisibleUsers();

  // Managers see all coverage in their scope ("X covers Y"); everyone else sees the
  // colleagues they personally cover.
  const teamQuery = useTeamCoverage(canManageTeam);
  const myQuery = useMyCoverage();
  const listLoading = canManageTeam ? teamQuery.isLoading : myQuery.isLoading;
  const listError = (canManageTeam ? teamQuery.error : myQuery.error) as Error | null;

  const subscribe = useSubscribeCoverage();
  const update = useUpdateCoverage();
  const unsubscribe = useUnsubscribeCoverage();
  const assign = useAssignCoverage();
  const revoke = useRevokeCoverageById();

  const [covererId, setCovererId] = useState(ME);
  const [targetId, setTargetId] = useState('');
  const [expiresAt, setExpiresAt] = useState('');
  const [redirect, setRedirect] = useState(true);
  const [removeTarget, setRemoveTarget] = useState<Row | null>(null);
  const [editId, setEditId] = useState('');
  const [editDate, setEditDate] = useState('');
  const [editRedirect, setEditRedirect] = useState(true);

  const rows: Row[] = useMemo(() => {
    if (canManageTeam) {
      return (teamQuery.data ?? []).map((c) => ({
        id: c.id,
        covererId: c.subscriber_id,
        covererName: c.subscriber_id === myId ? 'You' : c.subscriber_name ?? '—',
        isMeCoverer: c.subscriber_id === myId,
        coveredId: c.target_user_id,
        coveredName: c.target_user_name ?? '—',
        redirect: c.redirect_assignments,
        expiresAt: c.expires_at,
        assignedByName: c.assigned_by_hod ? c.created_by_name ?? 'a manager' : null,
        source: 'team' as const,
      }));
    }
    return (myQuery.data ?? []).map((c) => ({
      id: c.id,
      covererId: myId ?? ME,
      covererName: 'You',
      isMeCoverer: true,
      coveredId: c.target_user_id,
      coveredName: c.target_user_name ?? '—',
      redirect: c.redirect_assignments,
      expiresAt: c.expires_at,
      assignedByName: c.assigned_by_hod ? c.assigned_by_name ?? 'a manager' : null,
      source: 'mine' as const,
    }));
  }, [canManageTeam, teamQuery.data, myQuery.data, myId]);

  // Coverer options: "You" first, then scope-B colleagues (managers only).
  const covererOptions = useMemo(() => {
    const me = { id: ME, label: 'You' };
    if (!canManageTeam) return [me];
    return [me, ...visibleUsers.map((u) => ({ id: u.id, label: u.name || u.email }))];
  }, [canManageTeam, visibleUsers]);

  // Covered options: scope-B colleagues, never the chosen coverer.
  const resolvedCovererId = covererId === ME ? myId : covererId;
  const coveredOptions = useMemo(
    () =>
      visibleUsers
        .filter((u) => u.id !== resolvedCovererId)
        .map((u) => ({ id: u.id, label: u.name || u.email })),
    [visibleUsers, resolvedCovererId],
  );

  const adding = subscribe.isPending || assign.isPending;

  const resetForm = () => {
    setCovererId(ME);
    setTargetId('');
    setExpiresAt('');
    setRedirect(true);
  };

  const handleAdd = () => {
    if (!targetId) return;
    const expiresIso = expiresAt ? new Date(expiresAt).toISOString() : undefined;
    if (covererId === ME) {
      subscribe.mutate(
        { targetUserId: targetId, expiresAt: expiresIso, redirectAssignments: redirect },
        { onSuccess: resetForm },
      );
    } else {
      assign.mutate(
        { covererId, targetUserId: targetId, expiresAt: expiresIso, redirectAssignments: redirect },
        { onSuccess: resetForm },
      );
    }
  };

  const startEdit = (r: Row) => {
    setEditId(r.id);
    setEditDate(toDateInput(r.expiresAt));
    setEditRedirect(r.redirect);
  };
  const cancelEdit = () => {
    setEditId('');
    setEditDate('');
  };
  const handleSaveEdit = (r: Row) => {
    const expiresIso = editDate ? new Date(editDate).toISOString() : undefined;
    // Route the upsert: my own coverage uses the self endpoint; a manager editing
    // someone else's coverage re-assigns through the manage endpoint.
    if (r.isMeCoverer) {
      update.mutate(
        { targetUserId: r.coveredId, expiresAt: expiresIso, redirectAssignments: editRedirect },
        { onSuccess: cancelEdit },
      );
    } else {
      assign.mutate(
        {
          covererId: r.covererId,
          targetUserId: r.coveredId,
          expiresAt: expiresIso,
          redirectAssignments: editRedirect,
        },
        { onSuccess: cancelEdit },
      );
    }
  };

  const handleRemove = () => {
    if (!removeTarget) return;
    const r = removeTarget;
    const onSuccess = () => setRemoveTarget(null);
    if (r.source === 'team') {
      revoke.mutate(r.id, { onSuccess });
    } else {
      unsubscribe.mutate(r.coveredId, { onSuccess });
    }
  };

  return (
    <Card>
      <CardHeader className="gap-1">
        <CardTitle>Coverage</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* One form: coverer → covered, until, mode. */}
        <div className="flex flex-col gap-3 rounded-lg border bg-muted/30 p-3 sm:flex-row sm:items-end">
          <div className="flex-1 space-y-1.5">
            <Label>Coverer</Label>
            {canManageTeam ? (
              <Picker
                value={covererId}
                onChange={(id) => {
                  setCovererId(id);
                  if (id === targetId) setTargetId('');
                }}
                options={covererOptions}
                placeholder="Who covers"
                disabled={usersLoading || adding}
              />
            ) : (
              <div className="flex h-9 items-center rounded-md border bg-background px-3 text-sm text-muted-foreground">
                You
              </div>
            )}
          </div>
          <div className="hidden shrink-0 pb-2 text-muted-foreground sm:block">
            <ArrowRight className="size-4" />
          </div>
          <div className="flex-1 space-y-1.5">
            <Label>Covers for</Label>
            <Picker
              value={targetId}
              onChange={setTargetId}
              options={coveredOptions}
              placeholder="Who is away"
              disabled={usersLoading || adding}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="cov-until">Until (optional)</Label>
            <Input
              id="cov-until"
              type="date"
              value={expiresAt}
              onChange={(e) => setExpiresAt(e.target.value)}
              className="w-full sm:w-40"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="cov-mode">Mode</Label>
            <div className="flex h-9 items-center gap-2">
              <Switch id="cov-mode" checked={redirect} onCheckedChange={setRedirect} disabled={adding} />
              <span className="text-xs text-muted-foreground">{redirect ? 'Auto-assign' : 'Notify only'}</span>
            </div>
          </div>
          <Button onClick={handleAdd} disabled={!targetId || adding}>
            {adding ? (
              <LoaderCircleIcon className="animate-spin me-2 size-4" />
            ) : (
              <UserRoundPlus className="me-2 size-4" />
            )}
            Add
          </Button>
        </div>

        {/* One list: every coverage as "coverer → covered". */}
        {listError ? (
          <p className="text-sm text-destructive">{listError.message}</p>
        ) : listLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : rows.length === 0 ? (
          <div className="rounded-md border border-dashed px-4 py-8 text-center">
            <p className="text-sm text-muted-foreground">No active coverage yet.</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {canManageTeam
                ? 'Use the form above to arrange cover for a teammate who is away.'
                : 'Pick a colleague above to hold their incoming SLA tasks while they’re away.'}
            </p>
          </div>
        ) : (
          <ul className="divide-y rounded-md border">
            {rows.map((r) => {
              const editing = editId === r.id;
              const savingThis = (update.isPending || assign.isPending) && editing;
              return (
                <li key={r.id} className="flex items-center justify-between gap-3 px-4 py-3">
                  <div className="min-w-0">
                    <p className="flex flex-wrap items-center gap-1.5 text-sm font-medium">
                      <span className="truncate">{r.covererName}</span>
                      <ArrowRight className="size-3.5 shrink-0 text-muted-foreground" />
                      <span className="truncate">{r.coveredName}</span>
                    </p>
                    <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                      {editing ? (
                        <span className="flex items-center gap-1.5">
                          <Switch
                            checked={editRedirect}
                            onCheckedChange={setEditRedirect}
                            disabled={savingThis}
                            aria-label={`Mode for ${r.covererName} covering ${r.coveredName}`}
                          />
                          <span>{editRedirect ? 'Auto-assign' : 'Notify only'}</span>
                        </span>
                      ) : r.redirect ? (
                        <Badge variant="primary" appearance="ghost">Auto-assign</Badge>
                      ) : (
                        <Badge variant="secondary" appearance="ghost">Notify only</Badge>
                      )}
                      {r.assignedByName && !editing && (
                        <Badge variant="warning" appearance="ghost">Assigned by {r.assignedByName}</Badge>
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
                            aria-label={`End date for ${r.covererName} covering ${r.coveredName}`}
                          />
                          {editDate ? null : <span className="text-muted-foreground">(no end date)</span>}
                        </span>
                      ) : r.expiresAt ? (
                        <span>Until {formatDate(r.expiresAt)}</span>
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
                          onClick={() => handleSaveEdit(r)}
                          disabled={savingThis}
                          aria-label="Save coverage"
                        >
                          {savingThis ? <LoaderCircleIcon className="size-4 animate-spin" /> : <Check className="size-4" />}
                        </Button>
                        <Button variant="ghost" size="icon" onClick={cancelEdit} disabled={savingThis} aria-label="Cancel editing">
                          <X className="size-4" />
                        </Button>
                      </>
                    ) : (
                      <>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => startEdit(r)}
                          aria-label={`Edit ${r.covererName} covering ${r.coveredName}`}
                        >
                          <Pencil className="size-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="text-destructive hover:text-destructive"
                          onClick={() => setRemoveTarget(r)}
                          aria-label={`Remove ${r.covererName} covering ${r.coveredName}`}
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
              Remove coverage — {removeTarget?.covererName} covering {removeTarget?.coveredName}? Their SLA
              tasks will stop routing. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={revoke.isPending || unsubscribe.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={(e) => {
                e.preventDefault();
                handleRemove();
              }}
              disabled={revoke.isPending || unsubscribe.isPending}
            >
              {revoke.isPending || unsubscribe.isPending ? 'Removing…' : 'Remove'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
