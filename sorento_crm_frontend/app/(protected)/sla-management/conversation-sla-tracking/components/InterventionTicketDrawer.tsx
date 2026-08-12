'use client';

import { useEffect, useState } from 'react';
import { AlertCircle, CheckCircle2, MessageSquareQuote, Users } from 'lucide-react';

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
import RespondChatList from '@/components/common/RespondChatList';
import SharedConversationComposer from '@/components/common/conversation/SharedConversationComposer';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import type { RespondMessageRenderable } from '@/lib/respondIoChatRender';

import {
  useInterventionTicket,
  useInterventionTicketThread,
  useResolveInterventionTicket,
  useSendInterventionTicketMessage,
} from '../hooks/useInterventionTickets';
import TicketSlaChips from './TicketSlaChips';

interface InterventionTicketDrawerProps {
  ticketId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called after a resolve so the worklist can drop the row. */
  onResolved?: () => void;
}

/** Short excerpt of a message, used as the quoted text on a reply. */
function excerptOf(item: RespondMessageRenderable): string {
  const text = (item.message?.text ?? '').trim();
  if (text) return text;
  const type = String(item.message?.type ?? '').trim();
  return type ? `[${type}]` : '[attachment]';
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
}: InterventionTicketDrawerProps) {
  const [replyTo, setReplyTo] = useState<{ messageId: string | number | null; excerpt: string } | null>(
    null,
  );
  const [confirmResolve, setConfirmResolve] = useState(false);

  const ticketQuery = useInterventionTicket(open ? ticketId : null);
  const threadQuery = useInterventionTicketThread(open ? ticketId : null);
  const sendMutation = useSendInterventionTicketMessage(ticketId ?? '');
  const resolveMutation = useResolveInterventionTicket();

  // A different ticket means a different enquiry: never carry a quote across.
  useEffect(() => {
    setReplyTo(null);
  }, [ticketId]);

  const ticket = ticketQuery.data;
  const messages = threadQuery.data?.items ?? [];

  const handleResolve = () => {
    if (!ticketId) return;
    resolveMutation.mutate(ticketId, {
      onSuccess: () => {
        setConfirmResolve(false);
        onOpenChange(false);
        onResolved?.();
      },
    });
  };

  return (
    <>
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent
          side="right"
          className="flex w-full flex-col gap-3 overflow-y-auto p-4 sm:max-w-xl sm:p-6"
        >
          <SheetHeader className="pe-8">
            <SheetTitle className="break-words">
              {ticket?.contact_name ?? (ticketQuery.isLoading ? 'Loading enquiry…' : 'Enquiry')}
            </SheetTitle>
            <SheetDescription className="text-xs">
              {ticket?.contact_phone ?? 'Enquiry'}
            </SheetDescription>
          </SheetHeader>

          <SheetBody className="flex min-h-0 flex-1 flex-col gap-3 py-0">
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
                <div className="flex items-start gap-2">
                  <MessageSquareQuote className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                  <p className="min-w-0 whitespace-pre-wrap break-words text-sm">
                    {ticket.source_message_text?.trim() || 'No enquiry text captured.'}
                  </p>
                </div>
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

            {/* ---- The shared contact thread ---- */}
            {threadQuery.isLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-16 w-full" />
                <Skeleton className="h-16 w-full" />
                <Skeleton className="h-16 w-full" />
              </div>
            ) : threadQuery.isError ? (
              <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
                <AlertCircle className="mt-0.5 size-4 shrink-0" />
                <div className="min-w-0">
                  <p>
                    {threadQuery.error instanceof Error
                      ? threadQuery.error.message
                      : 'Failed to load the conversation.'}
                  </p>
                  <Button
                    size="sm"
                    variant="outline"
                    className="mt-2 h-7"
                    onClick={() => void threadQuery.refetch()}
                  >
                    Try again
                  </Button>
                </div>
              </div>
            ) : (
              <>
                {threadQuery.data?.error && (
                  <p className="text-xs text-muted-foreground">{threadQuery.data.error}</p>
                )}
                <RespondChatList
                  items={messages}
                  contactName={ticket?.contact_name}
                  contactPhone={ticket?.contact_phone}
                  emptyHint="No messages in this conversation yet."
                  maxHeightClass="max-h-[45vh]"
                  highlightMessageId={ticket?.source_message_id}
                  highlightLabel="This enquiry"
                  onReply={(item) =>
                    setReplyTo({ messageId: item.messageId ?? null, excerpt: excerptOf(item) })
                  }
                />
              </>
            )}

            {/* ---- Composer: text + attachments, quoted reply emulated ---- */}
            {ticket && (
              <SharedConversationComposer
                entityType="conversation_sla"
                entityId={ticket.id}
                canReply={ticket.can_send && !ticket.is_resolved}
                mode="conversation"
                attachmentsEnabled={ticket.send_capabilities.includes('attachment')}
                // A manual template send is a reply too: stamp THIS ticket, or
                // the response clock runs on while the contact has an answer.
                templateSendTrackingId={ticket.id}
                onSent={() => {
                  void ticketQuery.refetch();
                  void threadQuery.refetch();
                }}
                replyTo={replyTo}
                onClearReplyTo={() => setReplyTo(null)}
                windowStateOverride={{
                  closed: !ticket.window.open,
                  template: ticket.chat_template,
                }}
                sendAdapter={(payload) =>
                  sendMutation.mutateAsync({
                    text: payload.text,
                    attachments: payload.files,
                    reply_to_message_id:
                      payload.replyToMessageId != null ? String(payload.replyToMessageId) : null,
                    reply_to_excerpt: payload.replyToExcerpt ?? null,
                  })
                }
                notAvailableMessage={
                  ticket.is_resolved
                    ? 'This ticket is resolved.'
                    : 'Replying is not available for this contact.'
                }
              />
            )}
          </SheetBody>

          <div className="flex flex-col gap-2 border-t pt-3 sm:flex-row sm:justify-end">
            <Button
              variant="outline"
              disabled={!ticket?.can_resolve || ticket?.is_resolved}
              onClick={() => setConfirmResolve(true)}
            >
              <CheckCircle2 className="size-4" />
              Resolve ticket
            </Button>
          </div>
        </SheetContent>
      </Sheet>

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
    </>
  );
}
