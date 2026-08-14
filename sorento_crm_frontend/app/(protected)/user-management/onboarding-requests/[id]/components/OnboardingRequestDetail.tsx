'use client';

/**
 * The captain's review screen (UAC AC-6.2 to AC-6.7).
 *
 * It is the requester's grid plus what she could not see: collisions against
 * the live unique keys, the three-lane provisioning ledger, and the verdict
 * controls. Every section renders even when empty, with an explicit empty state
 * - a hidden section reads as data loss to whoever came looking for it.
 *
 * Read-only metadata (created, submitted, link expiry) lives in the header meta
 * strip and never inside an editable section, so the read view and the edit view
 * have exactly one structure between them.
 */

import { useCallback, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, Loader2, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { RecordNavigation } from '@/components/common/RecordNavigation';
import { PeopleGrid } from '@/components/common/onboarding/PeopleGrid';
import {
  ONBOARDING_STATUS_LABELS,
  type OnboardingPersonPatch,
} from '@/components/common/onboarding/types';
import { statusPillClass, STATUS_PILL_BASE } from '@/lib/status-pill';
import {
  approveOnboardingPerson,
  approveOnboardingRequest,
  deleteOnboardingRequest,
  getOnboardingRequest,
  listOnboardingRequests,
  rejectOnboardingPerson,
  startOnboardingReview,
  updateOnboardingPerson,
} from '../../services/onboardingService';

const BASE_PATH = '/user-management/onboarding-requests';

function formatMoment(value: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm truncate" title={value}>
        {value}
      </dd>
    </div>
  );
}

export function OnboardingRequestDetail({ requestId }: { requestId: string }) {
  const queryClient = useQueryClient();
  const [rejecting, setRejecting] = useState<{ id: string; name: string } | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const [deleteOpen, setDeleteOpen] = useState(false);

  const requestQuery = useQuery({
    queryKey: ['onboarding-request', requestId],
    queryFn: () => getOnboardingRequest(requestId),
  });

  // Neighbours for prev/next: reviewing a queue one request at a time is the
  // common case, and going back to the list between each is what makes a detail
  // page feel unfinished.
  const neighboursQuery = useQuery({
    queryKey: ['onboarding-requests', 'neighbours'],
    queryFn: () => listOnboardingRequests({ page: 1, limit: 100 }),
  });

  const request = requestQuery.data;

  const invalidate = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['onboarding-request', requestId] });
    queryClient.invalidateQueries({ queryKey: ['onboarding-requests'] });
  }, [queryClient, requestId]);

  const patchMutation = useMutation({
    mutationFn: ({ personId, patch }: { personId: string; patch: OnboardingPersonPatch }) =>
      updateOnboardingPerson(requestId, personId, patch),
    onSuccess: invalidate,
    onError: (e: Error) => toast.error(e.message),
  });

  const keepMutation = useMutation({
    mutationFn: (personId: string) => approveOnboardingPerson(requestId, personId),
    onSuccess: () => {
      invalidate();
      toast.success('Kept for provisioning');
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const rejectMutation = useMutation({
    mutationFn: ({ personId, reason }: { personId: string; reason: string }) =>
      rejectOnboardingPerson(requestId, personId, reason),
    onSuccess: () => {
      invalidate();
      setRejecting(null);
      setRejectReason('');
      toast.success('Row rejected. The requester sees the reason.');
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const startReviewMutation = useMutation({
    mutationFn: () => startOnboardingReview(requestId),
    onSuccess: () => {
      invalidate();
      toast.success('Review started');
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const approveMutation = useMutation({
    mutationFn: () => approveOnboardingRequest(requestId),
    onSuccess: () => {
      invalidate();
      toast.success('Approved. Provisioning has been queued.');
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const people = request?.people ?? [];
  const counts = useMemo(
    () => ({
      total: people.length,
      rejected: people.filter((p) => p.review_status === 'rejected').length,
      needsAgentSeat: people.filter((p) => p.needs_agent_seat).length,
      collisions: people.filter((p) => p.collisions.length > 0).length,
      failed: people.filter((p) => p.user_step === 'failed').length,
    }),
    [people],
  );

  if (requestQuery.isLoading) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-8 w-72" />
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (requestQuery.isError || !request) {
    return (
      <Alert variant="destructive">
        <AlertIcon />
        <AlertTitle>This onboarding request could not be loaded.</AlertTitle>
      </Alert>
    );
  }

  const canStartReview = request.status === 'submitted';
  const canApprove = request.status === 'in_review';

  return (
    <div className="flex flex-col gap-6">
      {/* Header: wraps on mobile so long titles never overlap the actions or
          push the page into horizontal overflow. */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 break-words">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-semibold break-words">{request.title}</h1>
            <span className={`${STATUS_PILL_BASE} ${statusPillClass(request.status)}`}>
              {ONBOARDING_STATUS_LABELS[request.status]}
            </span>
          </div>
          <p className="text-sm text-muted-foreground break-words">
            {request.company_name} · from {request.requester_name}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <RecordNavigation
            basePath={BASE_PATH}
            currentId={requestId}
            items={neighboursQuery.data?.data ?? []}
            ariaLabel="onboarding request"
          />
          {canStartReview ? (
            <Button
              variant="outline"
              onClick={() => startReviewMutation.mutate()}
              disabled={startReviewMutation.isPending}
            >
              Start review
            </Button>
          ) : null}
          {canApprove ? (
            <Button onClick={() => approveMutation.mutate()} disabled={approveMutation.isPending}>
              {approveMutation.isPending ? (
                <Loader2 className="size-4 mr-2 animate-spin" />
              ) : (
                <CheckCircle2 className="size-4 mr-2" />
              )}
              Approve and provision
            </Button>
          ) : null}
          <Button variant="outline" onClick={() => setDeleteOpen(true)}>
            <Trash2 className="size-4 mr-2" />
            Delete
          </Button>
        </div>
      </div>

      {/* Meta strip: read-only facts with no edit counterpart, so they live here
          rather than inside a section body. */}
      <dl className="grid grid-cols-2 gap-4 rounded-lg border p-4 sm:grid-cols-3 lg:grid-cols-6">
        <MetaItem label="Requester email" value={request.requester_email} />
        <MetaItem label="Created" value={formatMoment(request.created_at)} />
        <MetaItem label="Submitted" value={formatMoment(request.submitted_at)} />
        <MetaItem label="Link expires" value={formatMoment(request.expires_at)} />
        <MetaItem label="Reviewed by" value={request.reviewed_by_name ?? '—'} />
        <MetaItem label="Source file" value={request.source_file_name ?? 'Typed in'} />
      </dl>

      <Card>
        <CardHeader>
          <CardTitle>Notes from the requester</CardTitle>
        </CardHeader>
        <CardContent>
          {request.requester_note ? (
            <p className="text-sm whitespace-pre-wrap break-words">{request.requester_note}</p>
          ) : (
            <p className="text-sm text-muted-foreground">
              Nothing was added. Anything unusual would appear here.
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>People</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex flex-wrap gap-2 text-sm text-muted-foreground">
            <span>{counts.total} submitted</span>
            <span>·</span>
            <span>{counts.rejected} rejected</span>
            <span>·</span>
            <span>{counts.collisions} already exist</span>
            <span>·</span>
            <span>{counts.needsAgentSeat} need a chat-agent seat</span>
            {counts.failed ? (
              <>
                <span>·</span>
                <span className="text-red-700">{counts.failed} failed to provision</span>
              </>
            ) : null}
          </div>
          <PeopleGrid
            mode="review"
            people={people}
            templates={request.templates}
            onPatchPerson={(personId, patch) => patchMutation.mutate({ personId, patch })}
            onApprovePerson={(personId) => keepMutation.mutate(personId)}
            onRejectPerson={(personId) => {
              const person = people.find((p) => p.id === personId);
              setRejecting({ id: personId, name: person?.full_name ?? 'this person' });
              setRejectReason('');
            }}
            emptyMessage="Nobody has been submitted against this link yet."
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Provisioning</CardTitle>
        </CardHeader>
        <CardContent>
          {request.provisioned_at ? (
            <p className="text-sm">Provisioning ran at {formatMoment(request.provisioned_at)}.</p>
          ) : (
            <p className="text-sm text-muted-foreground">
              Nothing has been provisioned yet. Approving queues a background job; each person&apos;s
              lanes update on their row above as it runs.
            </p>
          )}
          <p className="mt-2 text-sm text-muted-foreground">
            This release creates CRM users. WhatsApp contacts and chat-agent seats are recorded
            but not yet created automatically.
          </p>
        </CardContent>
      </Card>

      {/* Reject: a reason is required, and it is required server-side too. */}
      <Dialog open={!!rejecting} onOpenChange={(open) => !open && setRejecting(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject {rejecting?.name}</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            <Label htmlFor="reject-reason">Why</Label>
            <Textarea
              id="reject-reason"
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="The requester sees this."
              rows={3}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejecting(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={!rejectReason.trim() || rejectMutation.isPending}
              onClick={() =>
                rejecting &&
                rejectMutation.mutate({ personId: rejecting.id, reason: rejectReason })
              }
            >
              Reject
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDeleteDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        description={
          <>
            Delete <strong>{request.title}</strong> and its {counts.total}{' '}
            {counts.total === 1 ? 'person' : 'people'}? This action cannot be undone.
          </>
        }
        onDelete={async () => {
          await deleteOnboardingRequest(requestId);
        }}
        queryKeysToInvalidate={[['onboarding-requests']]}
        successMessage="Onboarding request deleted"
        onSuccess={() => {
          window.location.assign(BASE_PATH);
        }}
      />
    </div>
  );
}
