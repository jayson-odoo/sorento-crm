'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { AlertCircle, CheckCircle2, History, MessageSquareQuote, Users } from 'lucide-react';
import { cn } from '@/lib/utils';

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
import RespondChatList from '@/components/common/RespondChatList';
import InternalCommentComposer from '@/components/common/conversation/InternalCommentComposer';
import SharedConversationComposer from '@/components/common/conversation/SharedConversationComposer';
import { useConversationThread } from '@/components/common/conversation/useConversationThread';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import type { RespondMessageRenderable } from '@/lib/respondIoChatRender';

import {
  useSlaTrackingConversation,
  useSlaTrackingMediaProxy,
  useSlaTrackingThreadLoaders,
} from '../hooks/useConversationSLATracking';
import {
  useDraftInterventionTicketReply,
  useInterventionTicket,
  useResolveInterventionTicket,
  useSendInterventionTicketMessage,
} from '../hooks/useInterventionTickets';
import { useCreateTicketComment, useTicketComments } from '../hooks/useTicketComments';
import { contactHistoryHref } from '../lib/historyLinks';
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
}

/** How often an open drawer re-reads the thread (paused in a background tab). */
const THREAD_POLL_MS = 10_000;

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
  onSent,
}: InterventionTicketDrawerProps) {
  const [replyTo, setReplyTo] = useState<{ messageId: string | number | null; excerpt: string } | null>(
    null,
  );
  const [confirmResolve, setConfirmResolve] = useState(false);
  // Reply talks to the contact; Comment never leaves the CRM. Two modes, one
  // switch, so nobody can WhatsApp a customer while meaning to leave a note.
  const [composerMode, setComposerMode] = useState<'reply' | 'comment'>('reply');

  const ticketQuery = useInterventionTicket(open ? ticketId : null);
  // The SAME query the SLA detail page's conversation panel uses (one key, one
  // cache entry): a send from here refreshes that panel too, and vice versa.
  // Polls while the drawer is open (and the tab is focused): a contact's reply
  // arrives on their schedule, not on ours, so an assignee reading the thread
  // must see it without hunting for a refresh. Stops the moment the drawer
  // closes, because the query is disabled with no ticket id.
  const threadQuery = useSlaTrackingConversation(open ? ticketId : null, {
    limit: 50,
    refetchIntervalMs: THREAD_POLL_MS,
  });
  const sendMutation = useSendInterventionTicketMessage(ticketId ?? '');
  const resolveMutation = useResolveInterventionTicket();
  const commentsQuery = useTicketComments(open ? ticketId : null);
  const commentMutation = useCreateTicketComment(ticketId ?? '');
  const aiDraftMutation = useDraftInterventionTicketReply(ticketId ?? '');

  // A different ticket means a different enquiry: never carry a quote across,
  // and never carry comment mode into someone else's conversation.
  useEffect(() => {
    setReplyTo(null);
    setComposerMode('reply');
  }, [ticketId]);

  const ticket = ticketQuery.data;
  const liveMessages = threadQuery.data?.items ?? [];

  // AC-L7 / AC-L8: scroll-back and search live in the SHARED thread hook, so the
  // SLA detail panel and the complaint / stock-inquiry / PR chat panels inherit
  // them by passing the same loaders - nothing here is drawer-specific.
  const { loadPage, searchMessages } = useSlaTrackingThreadLoaders(ticketId);
  // AC-N4: chat media has no CORS, so the preview reads its bytes through the
  // ticket-scoped backend proxy - that is what makes an .xlsx open inline here.
  const mediaProxy = useSlaTrackingMediaProxy(ticketId);
  const thread = useConversationThread({
    liveItems: liveMessages,
    loadPage,
    searchMessages,
    enabled: open && !!ticketId,
    resetKey: ticketId,
  });

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
    <>
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent
          side="right"
          className="flex w-full flex-col gap-3 overflow-y-auto p-4 sm:max-w-xl sm:p-6"
        >
          <SheetHeader className="pe-8">
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
            </div>
            <SheetDescription className="text-xs">
              {ticket?.contact_phone ?? 'Enquiry'}
            </SheetDescription>
          </SheetHeader>

          {/* ---- AC-N5: every ticket action lives here, in the header.
                  They used to sit in a footer under the composer, where they
                  crowded the toolbar and competed with the global assistant
                  launcher for the same corner. Own row rather than beside the
                  title: the sheet's close button owns the top-right corner. ---- */}
          <div
            data-testid="ticket-header-actions"
            className="flex flex-wrap items-center gap-2 border-b pb-3"
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
            <Button
              variant="outline"
              size="sm"
              className={isResolved ? '' : 'ms-auto'}
              disabled={!ticket?.can_resolve || isResolved}
              onClick={() => setConfirmResolve(true)}
            >
              <CheckCircle2 className="size-4" />
              Resolve ticket
            </Button>
          </div>

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
                {thread.error && <p className="text-xs text-destructive">{thread.error}</p>}
                <RespondChatList
                  items={thread.items}
                  contactName={ticket?.contact_name}
                  contactPhone={ticket?.contact_phone}
                  emptyHint="No messages in this conversation yet."
                  maxHeightClass="max-h-[45vh]"
                  highlightMessageId={ticket?.source_message_id}
                  highlightLabel="This enquiry"
                  onLoadOlder={thread.loadOlder}
                  hasMoreOlder={thread.hasMoreOlder}
                  isLoadingOlder={thread.isLoadingOlder}
                  atConversationStart={thread.atConversationStart}
                  isDetached={thread.isDetached}
                  onJumpToLatest={thread.jumpToLatest}
                  newerUnseenCount={thread.newerUnseenCount}
                  onLoadNewer={thread.loadNewer}
                  hasMoreNewer={thread.hasMoreNewer}
                  isLoadingNewer={thread.isLoadingNewer}
                  searchController={thread.search}
                  highlightTerm={thread.highlightTerm}
                  comments={commentsQuery.data ?? []}
                  mediaProxy={mediaProxy}
                  onReply={(item) =>
                    setReplyTo({ messageId: item.messageId ?? null, excerpt: excerptOf(item) })
                  }
                />
              </>
            )}

            {/* ---- Mode switch: message the contact, or note to the team ---- */}
            {ticket && (
              <div
                role="tablist"
                aria-label="Composer mode"
                className="flex w-full gap-1 rounded-md border bg-muted/40 p-1"
              >
                {(['reply', 'comment'] as const).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    role="tab"
                    aria-selected={composerMode === mode}
                    data-testid={`composer-mode-${mode}`}
                    onClick={() => setComposerMode(mode)}
                    className={cn(
                      'flex-1 rounded px-3 py-1.5 text-sm font-medium transition-colors',
                      composerMode === mode
                        ? mode === 'comment'
                          ? 'bg-amber-500 text-white shadow-sm'
                          : 'bg-background text-foreground shadow-sm'
                        : 'text-muted-foreground hover:text-foreground',
                    )}
                  >
                    {mode === 'reply' ? 'Reply' : 'Comment'}
                  </button>
                ))}
              </div>
            )}

            {/* ---- Composer: text + attachments, quoted reply emulated ---- */}
            {ticket && composerMode === 'comment' && (
              <InternalCommentComposer
                disabled={ticket.is_resolved}
                disabledMessage="This ticket is resolved."
                onSubmit={({ body, mentionedUserIds }) =>
                  commentMutation.mutateAsync({
                    body,
                    mentioned_user_ids: mentionedUserIds,
                  })
                }
              />
            )}

            {ticket && composerMode === 'reply' && (
              <SharedConversationComposer
                entityType="conversation_sla"
                entityId={ticket.id}
                canReply={ticket.can_send && !ticket.is_resolved}
                mode="conversation"
                attachmentsEnabled={ticket.send_capabilities.includes('attachment')}
                // A manual template send is a reply too: stamp THIS ticket, or
                // the response clock runs on while the contact has an answer.
                templateSendTrackingId={ticket.id}
                // Composer parity with Respond's own inbox (UAC AC-L4 / AC-L5).
                // Snippet variables resolve against THIS ticket, and the AI
                // draft is grounded on THIS thread - both server-side, so the
                // drawer only has to say which ticket it is.
                snippetsEnabled
                snippetTrackingId={ticket.id}
                emojiEnabled
                onAiAssist={async ({ instruction }) => {
                  const result = await aiDraftMutation.mutateAsync({ instruction });
                  return result.draft;
                }}
                onSent={() => {
                  void ticketQuery.refetch();
                  void threadQuery.refetch();
                  onSent?.();
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
