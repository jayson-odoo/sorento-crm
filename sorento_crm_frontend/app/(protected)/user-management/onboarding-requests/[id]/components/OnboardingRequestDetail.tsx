'use client';

/**
 * The captain's review screen (UAC AC-6.2 to AC-6.7).
 *
 * It is the requester's grid plus what she could not see: collisions against
 * the live unique keys, the three-lane provisioning ledger, and the verdict
 * controls. Every section renders even when empty, with an explicit empty state
 * - a hidden section reads as data loss to whoever came looking for it.
 *
 * The shell is the standard detail shell: a Toolbar carrying the breadcrumb,
 * the pager, the status-gated primary action and the gear menu, then stacked
 * cards. Read-only metadata (created, submitted, link expiry) lives in the meta
 * strip and never inside an editable section, so the read view and the edit view
 * have exactly one structure between them.
 */

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { CheckCircle2, Copy, KeyRound, Link2Off, Loader2, Send, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardHeading, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { DropdownMenuItem } from '@/components/ui/dropdown-menu';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { Container } from '@/components/common/container';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { DetailActionsMenu } from '@/components/common/DetailActionsMenu';
import DetailActions from '@/components/common/DetailActions';
import {
  Toolbar,
  ToolbarActions,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
import { PeopleGrid } from '@/components/common/onboarding/PeopleGrid';
import {
  ONBOARDING_STATUS_LABELS,
  ONBOARDING_STATUS_PILL_CODES,
} from '@/components/common/onboarding/types';
import { useCopyToClipboard } from '@/hooks/use-copy-to-clipboard';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { statusPillClass, STATUS_PILL_BASE } from '@/lib/status-pill';
import {
  useOnboardingRequest,
  useOnboardingRequestMutations,
} from '../../hooks/useOnboardingRequests';
import { onboardingPagerQuery } from '../../hooks/useOnboardingRequests';
import BackToList, { useBackToListHref } from '@/components/common/BackToList';

const BASE_PATH = '/user-management/onboarding-requests';

/**
 * The statuses the server still accepts reviewer writes on.
 *
 * Mirrors `REVIEWER_WRITABLE` in `app/services/onboarding_service.py`, which
 * answers 409 for everything else. An editable grid on a completed batch is a
 * screen full of dead controls: every keystroke and every verdict comes back
 * refused, and the reviewer only finds that out after trying.
 */
const REVIEWER_WRITABLE_STATUSES: string[] = ['submitted', 'in_review'];

/** Stored naive UTC, read as Malaysia wall-clock, never as the browser's zone. */
function moment(value: string | null): string {
  return value ? formatDateTimeInMalaysia(value) : '-';
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

function DetailShell({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Onboarding Request</ToolbarTitle>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/">Home</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>User Management</BreadcrumbPage>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbLink href={BASE_PATH}>Onboarding Requests</BreadcrumbLink>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
          {children}
        </Toolbar>
      </Container>
    </>
  );
}

/** Back carries the list query the row click wrote, so the queue reopens where it was. */
function BackToQueue() {
  return <BackToList listPath={BASE_PATH} label="Back to onboarding requests" />;
}

export function OnboardingRequestDetail({ requestId }: { requestId: string }) {
  const router = useRouter();
  const backHref = useBackToListHref(BASE_PATH);
  const [rejecting, setRejecting] = useState<{ id: string; name: string } | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const [deleteOpen, setDeleteOpen] = useState(false);

  const requestQuery = useOnboardingRequest(requestId);
  const request = requestQuery.data;

  const {
    patchPerson,
    approvePerson,
    rejectPerson,
    startReview,
    approveRequest,
    send,
    revoke,
    regenerate,
    remove,
  } = useOnboardingRequestMutations(requestId);

  const { copyToClipboard } = useCopyToClipboard({
    onCopy: () => toast.success('Link copied'),
  });

  const people = useMemo(() => request?.people ?? [], [request]);
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
      <>
        <DetailShell>
          <ToolbarActions>
            <BackToQueue />
          </ToolbarActions>
        </DetailShell>
        <Container>
          <div className="flex flex-col gap-4">
            <Skeleton className="h-8 w-72" />
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-64 w-full" />
          </div>
        </Container>
      </>
    );
  }

  if (requestQuery.isError || !request) {
    return (
      <>
        <DetailShell>
          <ToolbarActions>
            <BackToQueue />
          </ToolbarActions>
        </DetailShell>
        <Container>
          <Alert variant="destructive">
            <AlertIcon />
            <AlertTitle>This onboarding request could not be loaded.</AlertTitle>
          </Alert>
        </Container>
      </>
    );
  }

  const canStartReview = request.status === 'submitted';
  const canApprove = request.status === 'in_review';
  const linkLive = !request.revoked_at;
  const canAdministerLink = ['draft', 'sent'].includes(request.status);

  return (
    <>
      <DetailShell>
        <ToolbarActions>
          <BackToQueue />
        </ToolbarActions>
      </DetailShell>

      <Container>
        <div className="flex flex-col gap-6">
          {/* Meta: the record's own identity plus the read-only facts that have
              no edit counterpart, so they never sit inside a section body. */}
          <Card>
            <CardHeader className="flex-col items-stretch gap-3 sm:flex-row sm:items-start sm:justify-between">
              <CardHeading className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <CardTitle className="break-words">{request.title}</CardTitle>
                  <span
                    className={`${STATUS_PILL_BASE} ${statusPillClass(
                      ONBOARDING_STATUS_PILL_CODES[request.status],
                    )}`}
                  >
                    {ONBOARDING_STATUS_LABELS[request.status]}
                  </span>
                </div>
                <p className="text-sm text-muted-foreground break-words">
                  {request.company_name} · from {request.requester_name}
                </p>
              </CardHeading>
              <DetailActions
                pager={{
                  ...onboardingPagerQuery,
                  detailPath: BASE_PATH,
                  currentId: requestId,
                  ariaLabel: 'onboarding request',
                }}
                gear={
                  <DetailActionsMenu ariaLabel="Request actions">
                    <DropdownMenuItem
                      disabled={!request.intake_url || !linkLive}
                      onSelect={(e) => {
                        e.preventDefault();
                        if (request.intake_url) copyToClipboard(request.intake_url);
                      }}
                    >
                      <Copy className="size-4" />
                      Copy link
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      disabled={!linkLive || !canAdministerLink || revoke.isPending}
                      onSelect={(e) => {
                        e.preventDefault();
                        revoke.mutate();
                      }}
                    >
                      <Link2Off className="size-4" />
                      Revoke link
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      disabled={!canAdministerLink || regenerate.isPending}
                      onSelect={(e) => {
                        e.preventDefault();
                        regenerate.mutate();
                      }}
                    >
                      <KeyRound className="size-4" />
                      Issue a new link
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      variant="destructive"
                      onSelect={(e) => {
                        e.preventDefault();
                        setDeleteOpen(true);
                      }}
                    >
                      <Trash2 className="size-4" />
                      Delete
                    </DropdownMenuItem>
                  </DetailActionsMenu>
                }
                primary={
                  <>
                  {canStartReview ? (
                    <Button
                      variant="outline"
                      onClick={() => startReview.mutate()}
                      disabled={startReview.isPending}
                    >
                      Start review
                    </Button>
                  ) : null}
                  {canApprove ? (
                    <Button onClick={() => approveRequest.mutate()} disabled={approveRequest.isPending}>
                      {approveRequest.isPending ? (
                        <Loader2 className="size-4 animate-spin" />
                      ) : (
                        <CheckCircle2 className="size-4" />
                      )}
                      Approve and provision
                    </Button>
                  ) : null}
                  </>
                }
              />
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
                <MetaItem label="Requester email" value={request.requester_email} />
                <MetaItem label="Created" value={moment(request.created_at)} />
                <MetaItem label="Submitted" value={moment(request.submitted_at)} />
                <MetaItem label="Link expires" value={moment(request.expires_at)} />
                <MetaItem label="Reviewed by" value={request.reviewed_by_name ?? '-'} />
              </dl>
            </CardContent>
          </Card>

          {/* The link IS the product of creating a request (AC-3.3: revocable,
              re-sendable). Its state is shown; the token itself never is - a
              tokenised URL printed on screen is a credential on screen. */}
          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Intake link</CardTitle>
              </CardHeading>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              {request.revoked_at ? (
                <p className="text-sm text-destructive">
                  Revoked on {moment(request.revoked_at)}.
                </p>
              ) : request.intake_url ? (
                <p className="text-sm">Link active</p>
              ) : (
                <p className="text-sm text-muted-foreground">No intake link available.</p>
              )}
              {request.status === 'draft' ? (
                <div className="flex flex-wrap gap-2">
                  <Button onClick={() => send.mutate()} disabled={send.isPending}>
                    {send.isPending ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <Send className="size-4" />
                    )}
                    Send link
                  </Button>
                </div>
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Notes</CardTitle>
              </CardHeading>
            </CardHeader>
            <CardContent>
              {request.requester_note ? (
                <p className="text-sm whitespace-pre-wrap break-words">{request.requester_note}</p>
              ) : (
                <p className="text-sm text-muted-foreground">No notes.</p>
              )}
            </CardContent>
          </Card>

          <PeopleGrid
            mode="review"
            people={people}
            templates={request.templates}
            // Review mode with the pens taken away once the batch has left
            // review: the collision, lane and verdict columns still render -
            // they are what a finished batch is FOR - but nothing is offered
            // that the server would refuse.
            locked={!REVIEWER_WRITABLE_STATUSES.includes(request.status)}
            description={
              <span className="flex flex-wrap gap-1">
                <span>Submitted {counts.total}</span>
                <span>·</span>
                <span>Rejected {counts.rejected}</span>
                <span>·</span>
                <span>Existing {counts.collisions}</span>
                <span>·</span>
                <span>Respond.io accounts {counts.needsAgentSeat}</span>
                {counts.failed ? (
                  <>
                    <span>·</span>
                    <span className="text-destructive">Failed {counts.failed}</span>
                  </>
                ) : null}
              </span>
            }
            onPatchPerson={(personId, patch) => patchPerson.mutate({ personId, patch })}
            onApprovePerson={(personId) => approvePerson.mutate(personId)}
            onRejectPerson={(personId) => {
              const person = people.find((p) => p.id === personId);
              setRejecting({ id: personId, name: person?.full_name ?? 'this person' });
              setRejectReason('');
            }}
            emptyMessage="No people submitted yet."
          />

          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Provisioning</CardTitle>
              </CardHeading>
            </CardHeader>
            <CardContent>
              {request.provisioned_at ? (
                <p className="text-sm">Provisioning ran at {moment(request.provisioned_at)}.</p>
              ) : (
                <p className="text-sm text-muted-foreground">Nothing provisioned yet.</p>
              )}
            </CardContent>
          </Card>
        </div>
      </Container>

      {/* Reject: a reason is required, and it is required server-side too. */}
      <Dialog open={!!rejecting} onOpenChange={(open) => !open && setRejecting(null)}>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Reject {rejecting?.name}</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-2">
            <Label htmlFor="reject-reason">Reason</Label>
            <Textarea
              id="reject-reason"
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Reason for rejection"
              rows={3}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejecting(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={!rejectReason.trim() || rejectPerson.isPending}
              onClick={() => {
                if (!rejecting) return;
                rejectPerson.mutate(
                  { personId: rejecting.id, reason: rejectReason },
                  {
                    onSuccess: () => {
                      setRejecting(null);
                      setRejectReason('');
                    },
                  },
                );
              }}
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
          await remove.mutateAsync();
        }}
        queryKeysToInvalidate={[['onboarding-requests']]}
        successMessage="Onboarding request deleted"
        onSuccess={() => {
          router.push(backHref);
        }}
      />
    </>
  );
}
