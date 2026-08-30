'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  AlertCircle,
  CalendarPlus,
  CheckCircle2,
  History,
  MessageSquareQuote,
  Settings,
  UserRoundCog,
  Users,
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
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Skeleton } from '@/components/ui/skeleton';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useHasPermission } from '@/hooks/usePermissions';
import { formatDateTimeInMalaysia } from '@/lib/helpers';

import {
  useInterventionTicket,
  useResolveInterventionTicket,
} from '../hooks/useInterventionTickets';
import { useReassignSLATracking } from '../hooks/useTeamPendingSLA';
import { contactHistoryHref } from '../lib/historyLinks';
import ExtendDueDialog from './ExtendDueDialog';
import ReassignDialog from './ReassignDialog';
import TicketConversationPanel, { type TicketJumpRequest } from './TicketConversationPanel';
import TicketSlaChips from './TicketSlaChips';

interface InterventionTicketDrawerProps {
  ticketId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called after a resolve so the worklist can drop the row. */
  onResolved?: () => void;
  /**
   * Called after a reply goes out. The worklist behind this drawer loads
   * imperatively (getMyPendingSLA into state), not through react-query, so no
   * query invalidation reaches it - it has to be told, or the row keeps its
   * pre-reply countdown chips until the drawer closes.
   */
  onSent?: () => void;
  /**
   * Called after a reassign. The ticket has just left this user's worklist, so
   * the list behind the drawer has to re-read for the same imperative-load
   * reason `onSent` exists.
   */
  onReassigned?: () => void;
}

/**
 * The intervention ticket, opened in place from the dashboard worklist: enquiry
 * header (the message that triggered it), the full shared contact thread, and a
 * composer that stamps this ticket. Siblings for the same contact show the same
 * thread with their own header and clocks.
 */
export default function InterventionTicketDrawer({
  ticketId,
  open,
  onOpenChange,
  onResolved,
  onSent,
  onReassigned,
}: InterventionTicketDrawerProps) {
  const [confirmResolve, setConfirmResolve] = useState(false);
  const [reassignOpen, setReassignOpen] = useState(false);
  const [extendOpen, setExtendOpen] = useState(false);
  // Same slug the worklist row's Reassign is gated on (AC-B3 / AC-N7).
  const canReassign = useHasPermission(
    'sla_management.conversation_sla_tracking.reassign',
  );
  // Same slug the worklist row's Extend is gated on (AC-B4).
  const canExtend = useHasPermission('sla_management.conversation_sla_tracking.extend');
  const reassignMutation = useReassignSLATracking();
  /** Asks the panel's thread to scroll to the enquiry message (AC-N6). */
  const [jumpRequest, setJumpRequest] = useState<TicketJumpRequest | null>(null);

  const ticketQuery = useInterventionTicket(open ? ticketId : null);
  const ticket = ticketQuery.data;

  const resolveMutation = useResolveInterventionTicket();

  const handleResolve = () => {
    if (!ticketId) return;
    resolveMutation.mutate(ticketId, {
      onSuccess: () => {
        setConfirmResolve(false);
        // AC-M1: the drawer STAYS OPEN in a Resolved state. Closing it here (what
        // it used to do) yanked the conversation away mid-thought, right when the
        // assignee wants to re-read what they just agreed to. Refetching the
        // ticket is what flips it into that state: Resolved badge, disabled
        // composer with the reason on it, thread and notes still readable.
        void ticketQuery.refetch();
        // The worklist behind it drops the row as usual - it is no longer pending.
        onResolved?.();
      },
    });
  };

  const isResolved = !!ticket?.is_resolved;
  const historyHref = contactHistoryHref(ticket?.respond_io_id ?? ticket?.contact_phone);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="flex w-full flex-col gap-3 overflow-y-auto p-4 sm:max-w-2xl sm:p-6 lg:max-w-4xl"
      >
        <SheetHeader className="border-b pb-3 pe-8">
          <div className="flex flex-wrap items-center gap-2">
            <SheetTitle className="min-w-0 break-words">
              {ticket?.contact_name ?? (ticketQuery.isLoading ? 'Loading enquiry…' : 'Enquiry')}
            </SheetTitle>
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
            {/* ---- AC-N5: every ticket action lives here, in the header.
                    Sharing the title row (right-aligned, inside the pe-8 gutter
                    so the sheet's close button keeps the corner) rather than a
                    row of their own: the second row cost the thread a whole
                    button-height of reading room. ---- */}
            <div
              data-testid="ticket-header-actions"
              className="ms-auto flex flex-wrap items-center justify-end gap-2"
            >
          {isResolved && (
            <p
              className="me-auto text-xs text-muted-foreground"
              data-testid="ticket-resolved-at"
            >
              Resolved {ticket?.resolved_at ? formatDateTimeInMalaysia(ticket.resolved_at) : ''}
            </p>
          )}
          {/* AC-M2: the one-click path back to the full trail for this contact,
              offered exactly when the ticket has just left the pending list. */}
          {isResolved && (
            <Button variant="outline" size="sm" asChild data-testid="ticket-history-link">
              <Link href={historyHref}>
                <History className="size-4" />
                View history
              </Link>
            </Button>
          )}
          {/* AC-N7: the same dialog the worklist row opens, never a fork. */}
          {canReassign && (
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
          <Button
            variant="outline"
            size="sm"
            disabled={!ticket?.can_resolve || isResolved}
            onClick={() => setConfirmResolve(true)}
          >
            <CheckCircle2 className="size-4" />
            Resolve ticket
          </Button>
          {/* Overflow. Extend lives here rather than as a fourth header button:
              the header is already at its width on a phone, and every further
              ticket action belongs in this menu instead of beside it. Gated on
              the same slug + resolution-deadline rule as the worklist row's
              Extend (AC-B4), so the menu is absent when it would hold nothing. */}
          {canExtend && !isResolved && ticket?.due_at_resolution && (
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
            {ticket?.contact_phone ?? 'Enquiry'}
          </SheetDescription>
        </SheetHeader>

        <SheetBody className="flex min-h-0 flex-1 flex-col gap-3 pt-0 pb-6">
          {/* ---- Enquiry reference: what this ticket is actually about ---- */}
          {ticketQuery.isLoading ? (
            <Skeleton className="h-24 w-full" />
          ) : ticketQuery.isError ? (
            <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
              <AlertCircle className="mt-0.5 size-4 shrink-0" />
              <div className="min-w-0">
                <p>
                  {ticketQuery.error instanceof Error
                    ? ticketQuery.error.message
                    : 'Failed to load this ticket.'}
                </p>
                <Button
                  size="sm"
                  variant="outline"
                  className="mt-2 h-7"
                  onClick={() => void ticketQuery.refetch()}
                >
                  Try again
                </Button>
              </div>
            </div>
          ) : ticket ? (
            <div className="rounded-md border bg-muted/30 p-3">
              {/* AC-N6: the quote is the way INTO the thread. Clicking it
                  scrolls to the message that started this ticket, fetching
                  the surrounding page first when the reader has scrolled
                  past it. Only a button when there is a message to reach. */}
              {ticket.source_message_id ? (
                <button
                  type="button"
                  data-testid="enquiry-quote-jump"
                  aria-label="Show this message in the conversation"
                  onClick={() =>
                    setJumpRequest((prev) => ({
                      messageId: ticket.source_message_id,
                      nonce: (prev?.nonce ?? 0) + 1,
                    }))
                  }
                  className="flex w-full items-start gap-2 rounded text-start transition-colors hover:bg-black/5 dark:hover:bg-white/10"
                >
                  <MessageSquareQuote className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                  <span className="min-w-0 whitespace-pre-wrap break-words text-sm">
                    {ticket.source_message_text?.trim() || 'No enquiry text captured.'}
                  </span>
                </button>
              ) : (
                <div className="flex items-start gap-2">
                  <MessageSquareQuote className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                  <p className="min-w-0 whitespace-pre-wrap break-words text-sm">
                    {ticket.source_message_text?.trim() || 'No enquiry text captured.'}
                  </p>
                </div>
              )}
              <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                <span className="inline-flex items-center gap-1">
                  <Users className="size-3" />
                  {ticket.team_label ?? 'Unassigned team'}
                </span>
                <span>Requested {formatDateTimeInMalaysia(ticket.initiated_at)}</span>
                {ticket.policy_name && <span>{ticket.policy_name}</span>}
              </div>
              <TicketSlaChips
                className="mt-2"
                dueAt={ticket.due_at}
                dueAtResolution={ticket.due_at_resolution}
                extensionCount={ticket.extension_count}
                isResponded={ticket.is_responded}
                respondedAt={ticket.responded_at}
                currentTier={ticket.current_tier}
                escalatedAt={ticket.escalated_at}
              />
              {ticket.escalated_at && ticket.escalation_reason && (
                <p className="mt-2 text-xs text-amber-700 dark:text-amber-400">
                  {ticket.escalation_reason}
                </p>
              )}
            </div>
          ) : null}

          {/* ---- The chat panel: thread, notes, composers. The SAME
                  component the SLA detail page's "Chat Records" mounts, so a
                  capability cannot land on one surface and not the other. ---- */}
          {/* The thread takes whatever height the header and the enquiry card
              leave, and the composer stays on screen: a viewport-capped list
              inside a scrolling sheet put the toolbar on the bottom edge on
              every laptop. min-h keeps a readable strip on a short phone. */}
          <TicketConversationPanel
            ticketId={ticketId}
            enabled={open}
            className="min-h-0 flex-1"
            maxHeightClass="min-h-40 flex-1"
            jumpRequest={jumpRequest}
            onSent={onSent}
          />
        </SheetBody>

        {/* ---- Both of these live INSIDE the Sheet, not after it.
                Radix decides "did the user click outside me?" by walking the
                REACT tree, not the DOM (portalled content still bubbles to its
                React parent). Rendered as siblings of <Sheet>, every pointerdown
                in the reassign dialog or its dropdown read as an outside click on
                the drawer, which dismissed it: the panel visibly dropped away and
                `ticketId` went null, so the Reassign button then did nothing. ---- */}
        <ReassignDialog
          open={reassignOpen}
          onOpenChange={setReassignOpen}
          taskLabel={ticket?.contact_name ? `this enquiry from ${ticket.contact_name}` : null}
          submitting={reassignMutation.isPending}
          onConfirm={(userId) => {
            if (!ticketId) return;
            reassignMutation.mutate(
              { id: ticketId, userId },
              {
                onSuccess: () => {
                  setReassignOpen(false);
                  // The viewer may no longer be able to act on it: re-read the
                  // ticket so the composer and the actions say so.
                  void ticketQuery.refetch();
                  onReassigned?.();
                },
              },
            );
          }}
        />

        {/* The SAME dialog the worklist row's Extend opens (AC-B4), never a
            fork - and inside the Sheet for the Radix reason above. Mounted only
            while open: it debounces a preview call off its own state, which a
            permanently-mounted copy would carry for every drawer. */}
        {extendOpen && (
          <ExtendDueDialog
            open
            onOpenChange={setExtendOpen}
            trackingId={ticketId ?? ''}
            currentDueAt={ticket?.due_at_resolution ?? null}
            label={ticket?.contact_name ? `Enquiry from ${ticket.contact_name}` : undefined}
            // The header chips read the ticket, so the new deadline only shows
            // once the ticket is re-read.
            onExtended={() => void ticketQuery.refetch()}
          />
        )}

        <AlertDialog open={confirmResolve} onOpenChange={setConfirmResolve}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Mark as resolved</AlertDialogTitle>
              <AlertDialogDescription>
                This stops the SLA clock for this enquiry only. Other open enquiries from{' '}
                {ticket?.contact_name ?? 'this contact'} stay open. This action cannot be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={resolveMutation.isPending}>Cancel</AlertDialogCancel>
              <AlertDialogAction
                onClick={(e) => {
                  e.preventDefault();
                  handleResolve();
                }}
                disabled={resolveMutation.isPending}
              >
                {resolveMutation.isPending ? 'Resolving…' : 'Confirm'}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </SheetContent>
    </Sheet>
  );
}
