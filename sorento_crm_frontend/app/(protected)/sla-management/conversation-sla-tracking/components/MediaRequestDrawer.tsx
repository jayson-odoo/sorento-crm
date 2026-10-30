'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  AlertCircle,
  CalendarPlus,
  CheckCircle2,
  Package,
  Settings,
  UserRoundCog,
} from 'lucide-react';

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
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Skeleton } from '@/components/ui/skeleton';
import { useHasPermission } from '@/hooks/usePermissions';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { toast } from '@/lib/toast';

import { useMediaRequest } from '../hooks/useMediaRequest';
import { useReassignSLATracking } from '../hooks/useTeamPendingSLA';
import { actOnDrawingRequest } from '../services/conversationSLATrackingService';
import ExtendDueDialog from './ExtendDueDialog';
import ReassignDialog from './ReassignDialog';
import TicketSlaChips from './TicketSlaChips';

export interface MediaRequestDrawerProps {
  /** The tracking id of the drawing or photo task. */
  ticketId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** After a resolve, so the worklist can drop the row. */
  onResolved?: () => void;
  /** After a respond, so the row's chips and button follow. */
  onSent?: () => void;
  onReassigned?: () => void;
}

const NOUN = { drawing: 'Product drawing', photo: 'Product photo' } as const;

/**
 * The side panel of a product drawing or photo task, the media mode of the chat ticket panel:
 * the same sheet shell, header actions (Reassign, Respond, Resolve ticket with its confirm,
 * overflow Extend) and SLA chips, with the task's own body in place of the thread. The file is
 * uploaded elsewhere (Resources), so the panel only links there.
 */
export default function MediaRequestDrawer({
  ticketId,
  open,
  onOpenChange,
  onResolved,
  onSent,
  onReassigned,
}: MediaRequestDrawerProps) {
  const [confirmResolve, setConfirmResolve] = useState(false);
  const [reassignOpen, setReassignOpen] = useState(false);
  const [extendOpen, setExtendOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const canReassign = useHasPermission(
    'sla_management.conversation_sla_tracking.reassign',
  );
  const canExtend = useHasPermission(
    'sla_management.conversation_sla_tracking.extend',
  );
  const reassignMutation = useReassignSLATracking();

  const query = useMediaRequest(open ? ticketId : null);
  const request = query.data;
  const isResolved = !!request?.is_resolved;
  const code = request?.product_code ?? '';
  const title = request
    ? `${NOUN[request.kind]} · ${code}`
    : query.isLoading
      ? 'Loading request…'
      : 'Request';

  const act = async (action: 'respond' | 'resolve') => {
    if (!ticketId) return;
    setBusy(true);
    try {
      await actOnDrawingRequest(ticketId, action);
      toast.success(
        action === 'respond' ? 'Marked as responded' : 'Request resolved',
      );
      setConfirmResolve(false);
      await query.refetch();
      // The worklist is loaded imperatively, so it has to be told either way.
      if (action === 'resolve') onResolved?.();
      else onSent?.();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : `Failed to ${action}`);
    } finally {
      setBusy(false);
    }
  };

  const showExtend = canExtend && !isResolved && !!request?.due_at_resolution;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="flex w-full flex-col gap-3 overflow-hidden p-4 sm:max-w-2xl sm:p-6 lg:max-w-4xl"
      >
        <SheetHeader className="border-b pb-3 pe-8">
          <div className="flex flex-wrap items-center gap-2">
            <SheetTitle className="min-w-0 break-words">{title}</SheetTitle>
            {isResolved && (
              <Badge
                variant="success"
                appearance="light"
                size="sm"
                data-testid="ticket-resolved-badge"
              >
                <CheckCircle2 className="size-3" />
                Resolved
              </Badge>
            )}
            <div
              data-testid="ticket-header-actions"
              className="ms-auto flex flex-wrap items-center justify-end gap-2"
            >
              {isResolved && request?.resolved_at && (
                <p
                  className="me-auto text-xs text-muted-foreground"
                  data-testid="ticket-resolved-at"
                >
                  Resolved {formatDateTimeInMalaysia(request.resolved_at)}
                </p>
              )}
              {canReassign && request?.assignee_team_id && (
                <Button
                  variant="outline"
                  size="sm"
                  data-testid="ticket-reassign"
                  disabled={isResolved || reassignMutation.isPending}
                  onClick={() => setReassignOpen(true)}
                >
                  <UserRoundCog className="size-4" />
                  Reassign
                </Button>
              )}
              {request && !request.is_responded && !isResolved && (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busy || !request.is_assignee}
                  onClick={() => void act('respond')}
                >
                  Respond
                </Button>
              )}
              <Button
                variant="outline"
                size="sm"
                disabled={!request?.can_resolve || isResolved || busy}
                title={
                  !isResolved && request && !request.can_resolve
                    ? `Assigned to ${request.assignee_name ?? 'someone else'}`
                    : undefined
                }
                onClick={() => setConfirmResolve(true)}
              >
                <CheckCircle2 className="size-4" />
                Resolve ticket
              </Button>
              {showExtend && (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="outline"
                      size="sm"
                      data-testid="ticket-overflow"
                      aria-label="More ticket actions"
                    >
                      <Settings className="size-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem
                      data-testid="ticket-extend"
                      onSelect={() => setExtendOpen(true)}
                    >
                      <CalendarPlus className="size-4 mr-2" />
                      Extend
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </div>
          </div>
          <SheetDescription className="text-xs">
            {request?.assignee_name
              ? `With ${request.assignee_name}`
              : 'Request'}
          </SheetDescription>
        </SheetHeader>

        <SheetBody className="flex min-h-0 flex-1 flex-col gap-4 pt-0 pb-6">
          {query.isLoading ? (
            <Skeleton className="h-24 w-full" />
          ) : query.isError ? (
            <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
              <AlertCircle className="mt-0.5 size-4 shrink-0" />
              <div className="min-w-0">
                <p>
                  {query.error instanceof Error
                    ? query.error.message
                    : 'Failed to load this request.'}
                </p>
                <Button
                  size="sm"
                  variant="outline"
                  className="mt-2 h-7"
                  onClick={() => void query.refetch()}
                >
                  Try again
                </Button>
              </div>
            </div>
          ) : request ? (
            <>
              <div className="rounded-md border bg-muted/30 p-3">
                <div className="flex items-start gap-2">
                  <Package className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 text-sm">
                    <Link
                      href={request.product_href}
                      className="font-medium text-primary hover:underline"
                    >
                      {request.product_code}
                    </Link>
                    {request.product_name && (
                      <span className="text-muted-foreground">
                        {' '}
                        {request.product_name}
                      </span>
                    )}
                  </div>
                </div>
                <TicketSlaChips
                  className="mt-2"
                  dueAt={request.due_at}
                  dueAtResolution={request.due_at_resolution}
                  extensionCount={request.extension_count}
                  isResponded={request.is_responded}
                  respondedAt={request.responded_at}
                  currentTier={request.current_tier}
                  escalatedAt={request.escalated_at}
                />
                <p className="mt-2 text-xs">
                  <Link
                    href={request.resources_href}
                    className="font-medium text-primary hover:underline"
                  >
                    Upload in Resources
                  </Link>
                </p>
              </div>

              <section aria-labelledby="media-quotations-heading">
                <h3
                  id="media-quotations-heading"
                  className="text-sm font-medium"
                >
                  Waiting on this
                </h3>
                {request.quotations.length === 0 ? (
                  <div data-testid="media-quotations-empty" className="mt-1">
                    <p className="text-sm text-muted-foreground">
                      No quotation is waiting
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Quotations appear here when a salesperson escalates from
                      them.
                    </p>
                  </div>
                ) : (
                  <ul className="mt-1 space-y-1 text-sm">
                    {request.quotations.map((quotation) => (
                      <li key={quotation.quotation_id}>
                        <Link
                          href={quotation.href}
                          className="text-primary hover:underline"
                        >
                          {quotation.label}
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section aria-labelledby="media-followers-heading">
                <h3
                  id="media-followers-heading"
                  className="text-sm font-medium"
                >
                  Following
                </h3>
                {request.followers.length === 0 ? (
                  <div data-testid="media-followers-empty" className="mt-1">
                    <p className="text-sm text-muted-foreground">
                      Nobody is following
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Everyone who escalates is told when it is resolved.
                    </p>
                  </div>
                ) : (
                  <ul className="mt-1 space-y-0.5 text-sm">
                    {request.followers.map((name, index) => (
                      <li key={`${name}-${index}`}>{name}</li>
                    ))}
                  </ul>
                )}
              </section>
            </>
          ) : null}
        </SheetBody>

        <ReassignDialog
          open={reassignOpen}
          onOpenChange={setReassignOpen}
          taskLabel={request ? `${NOUN[request.kind]} · ${code}` : null}
          submitting={reassignMutation.isPending}
          onConfirm={(userId) => {
            if (!ticketId) return;
            reassignMutation.mutate(
              { id: ticketId, userId },
              {
                onSuccess: () => {
                  setReassignOpen(false);
                  void query.refetch();
                  onReassigned?.();
                },
              },
            );
          }}
        />

        {extendOpen && (
          <ExtendDueDialog
            open
            onOpenChange={setExtendOpen}
            trackingId={ticketId ?? ''}
            currentDueAt={request?.due_at_resolution ?? null}
            label={request ? `${NOUN[request.kind]} · ${code}` : undefined}
            onExtended={() => void query.refetch()}
          />
        )}

        <AlertDialog open={confirmResolve} onOpenChange={setConfirmResolve}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Mark as resolved</AlertDialogTitle>
              <AlertDialogDescription>
                This stops the SLA clock and tells everyone who escalated it.
                This action cannot be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel>
              <AlertDialogAction
                onClick={(e) => {
                  e.preventDefault();
                  void act('resolve');
                }}
                disabled={busy}
              >
                {busy ? 'Resolving…' : 'Confirm'}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </SheetContent>
    </Sheet>
  );
}
