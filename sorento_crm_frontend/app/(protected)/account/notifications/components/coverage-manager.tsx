'use client';

import { useMemo, useState } from 'react';
import { useSession } from 'next-auth/react';
import {
  ArrowRight,
  Check,
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
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { useVisibleUsers } from '@/app/(protected)/sla-management/conversation-sla-tracking/hooks/useTeamPendingSLA';
import {
  useAssignCoverage,
  useCoverageForMe,
  useMyCoverage,
  useNominateCoverage,
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
  /** Canonical role-explicit sentence from the backend (real names, not "You"). Rendered
   * sr-only so the page snapshot the AI assistant reads is unambiguous about who covers
   * whom vs who assigned it - the compact "name → name" row flattens that distinction. */
  summary: string | null;
  /** 'mine' = I'm the coverer (self endpoint); 'team' = HoD-managed row; 'for-me' =
   * a colleague covers me (revoke by id, edit via nominate). */
  source: 'mine' | 'team' | 'for-me';
}

interface PickerProps {
  value: string;
  onChange: (id: string) => void;
  options: { id: string; label: string }[];
  placeholder: string;
  disabled?: boolean;
}

function Picker({ value, onChange, options, placeholder, disabled }: PickerProps) {
  return (
    <SearchableSelect
      value={value}
      onChange={onChange}
      options={options.map((o) => ({ value: o.id, label: o.label }))}
      placeholder={placeholder}
      emptyMessage="No colleagues available."
      disabled={disabled}
      triggerClassName="w-full"
    />
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
  // Non-managers also see who covers THEM (self-nominated or HoD-arranged). Managers
  // already see for-me rows inside their team-scope view, so skip the extra fetch.
  const forMeQuery = useCoverageForMe(!canManageTeam);
  const listLoading = canManageTeam
    ? teamQuery.isLoading
    : myQuery.isLoading || forMeQuery.isLoading;
  const listError = (canManageTeam
    ? teamQuery.error
    : myQuery.error || forMeQuery.error) as Error | null;

  const subscribe = useSubscribeCoverage();
  const update = useUpdateCoverage();
  const unsubscribe = useUnsubscribeCoverage();
  const assign = useAssignCoverage();
  const nominate = useNominateCoverage();
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
        covererName: c.subscriber_id === myId ? 'You' : c.subscriber_name ?? '-',
        isMeCoverer: c.subscriber_id === myId,
        coveredId: c.target_user_id,
        coveredName: c.target_user_name ?? '-',
        redirect: c.redirect_assignments,
        expiresAt: c.expires_at,
        assignedByName: c.assigned_by_hod ? c.created_by_name ?? 'a manager' : null,
        summary: c.summary ?? null,
        source: 'team' as const,
      }));
    }
    const mine: Row[] = (myQuery.data ?? []).map((c) => ({
      id: c.id,
      covererId: myId ?? ME,
      covererName: 'You',
      isMeCoverer: true,
      coveredId: c.target_user_id,
      coveredName: c.target_user_name ?? '-',
      redirect: c.redirect_assignments,
      expiresAt: c.expires_at,
      assignedByName: c.assigned_by_hod ? c.assigned_by_name ?? 'a manager' : null,
      summary: c.summary ?? null,
      source: 'mine' as const,
    }));
    // Colleagues who cover ME (self-nominated or HoD-arranged). Shown so I can see +
    // cancel my own cover. De-dupe against `mine` by id (a self-cover can't be both).
    const seen = new Set(mine.map((r) => r.id));
    const forMe: Row[] = (forMeQuery.data ?? [])
      .filter((c) => !seen.has(c.id))
      .map((c) => ({
        id: c.id,
        covererId: c.subscriber_id,
        covererName: c.subscriber_name ?? '-',
        isMeCoverer: false,
        coveredId: myId ?? ME,
        coveredName: 'You',
        redirect: c.redirect_assignments,
        expiresAt: c.expires_at,
        assignedByName: c.assigned_by_hod ? c.assigned_by_name ?? 'a manager' : null,
        summary: c.summary ?? null,
        source: 'for-me' as const,
      }));
    return [...mine, ...forMe];
  }, [canManageTeam, teamQuery.data, myQuery.data, forMeQuery.data, myId]);

  // Coverer options: "You" first, then scope-B colleagues. Everyone can pick a
  // colleague now - a non-manager doing so can only cover THEMSELVES (self-nominate).
  const covererOptions = useMemo(() => {
    const me = { id: ME, label: 'You' };
    return [me, ...visibleUsers.map((u) => ({ id: u.id, label: u.name || u.email }))];
  }, [visibleUsers]);

  // Covered options: scope-B colleagues, never the chosen coverer. "You" is offered
  // when the coverer is someone else (a colleague covering me). A non-manager who
  // picked a colleague as coverer may ONLY cover themselves.
  const resolvedCovererId = covererId === ME ? myId : covererId;
  const coveredOptions = useMemo(() => {
    const me = myId ? [{ id: myId, label: 'You' }] : [];
    if (!canManageTeam && covererId !== ME) return me;
    const colleagues = visibleUsers
      .filter((u) => u.id !== resolvedCovererId)
      .map((u) => ({ id: u.id, label: u.name || u.email }));
    // Offer "You" as the covered party only when a colleague is the coverer.
    return covererId !== ME ? [...me, ...colleagues] : colleagues;
  }, [canManageTeam, covererId, visibleUsers, resolvedCovererId, myId],
  );

  const adding = subscribe.isPending || assign.isPending || nominate.isPending;

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
      // I cover a colleague.
      subscribe.mutate(
        { targetUserId: targetId, expiresAt: expiresIso, redirectAssignments: redirect },
        { onSuccess: resetForm },
      );
    } else if (targetId === myId) {
      // A colleague covers ME - self-service nominate (no manager permission needed).
      nominate.mutate(
        { covererId, expiresAt: expiresIso, redirectAssignments: redirect },
        { onSuccess: resetForm },
      );
    } else {
      // Manager arranging cover between two other people.
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
    // Route the upsert: my own coverage uses the self endpoint; coverage OF me
    // re-nominates (self-service); a manager editing someone else's re-assigns.
    if (r.isMeCoverer) {
      update.mutate(
        { targetUserId: r.coveredId, expiresAt: expiresIso, redirectAssignments: editRedirect },
        { onSuccess: cancelEdit },
      );
    } else if (r.source === 'for-me') {
      nominate.mutate(
        { covererId: r.covererId, expiresAt: expiresIso, redirectAssignments: editRedirect },
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
    // 'mine' = I'm the coverer → delete by (me, target). 'team'/'for-me' = revoke by
    // row id (deactivate_by_id permits the coverer, the covered party, or a HoD).
    if (r.source === 'mine') {
      unsubscribe.mutate(r.coveredId, { onSuccess });
    } else {
      revoke.mutate(r.id, { onSuccess });
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
            <Picker
              value={covererId}
              onChange={(id) => {
                setCovererId(id);
                // Reset the covered party when it clashes with the new coverer, or
                // when a non-manager switches to a colleague-coverer (then only
                // "You" is valid as the covered party).
                if (id === targetId || (!canManageTeam && id !== ME)) setTargetId('');
              }}
              options={covererOptions}
              placeholder="Who covers"
              disabled={usersLoading || adding}
            />
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
          <Button data-guide-target="dashboard.coverage.add" onClick={handleAdd} disabled={!targetId || adding}>
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
                    {/* Canonical role-explicit sentence - invisible on screen but present in
                        the DOM (sr-only is captured by innerText), so the AI page snapshot and
                        screen readers get an unambiguous "X covers for Y, assigned by Z" instead
                        of the compact "X → Y" that flattens the roles. */}
                    {r.summary && <span className="sr-only">{r.summary}</span>}
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
                        <Badge variant="primary">Auto-assign</Badge>
                      ) : (
                        <Badge variant="secondary">Notify only</Badge>
                      )}
                      {r.assignedByName && !editing && (
                        <Badge variant="warning">Assigned by {r.assignedByName}</Badge>
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
              Remove coverage - {removeTarget?.covererName} covering {removeTarget?.coveredName}? Their SLA
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
