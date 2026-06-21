'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import {
  AlertCircle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  ExternalLink,
  TrendingUp,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
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
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

const PAGE_SIZE = 5;
const MAX_TIER = 3;
import {
  getMyPendingSLA,
  resolveConversationSLATracking,
  escalateConversationSLATracking,
  type MyPendingSLAItem,
} from '../services/conversationSLATrackingService';

// Same inbox base used by the SLA detail page; conversation rows deep-link here
// because the CRM cannot send files in-app yet — staff reply from Respond.
const RESPOND_IO_INBOX_BASE_URL = 'https://app.respond.io/space/364817/inbox';

const ENTITY_ROUTES: Record<string, { base: string; label: string }> = {
  stock_inquiry: { base: '/procurement-management/stock-inquiries', label: 'Stock inquiry' },
  complaint: { base: '/complaint-management/complaints', label: 'Complaint' },
  purchase_request: { base: '/procurement-management/purchase-requests', label: 'Purchase request' },
  sponsorship_form: { base: '/procurement-management/purchase-requests', label: 'Sponsorship form' },
};

/** Form-vs-conversation is decided by the backend (is_form_sla, from FORM_SLA_TYPES)
 * — never re-derived here, or types the FE route map doesn't know (e.g. 'ticket')
 * silently fall through to the conversation branch. */
function isFormTask(item: MyPendingSLAItem): boolean {
  return item.is_form_sla;
}

/** In-system record link when we have a known route for the form type; null when we
 * don't (e.g. ticket — the row falls back to its Respond conversation / SLA detail). */
function entityHref(item: MyPendingSLAItem): string | null {
  const route = ENTITY_ROUTES[item.source_entity_type ?? ''];
  if (route && item.source_entity_id) return `${route.base}/${item.source_entity_id}`;
  return null;
}

function humanizeType(item: MyPendingSLAItem): string {
  const route = ENTITY_ROUTES[item.source_entity_type ?? ''];
  if (route) return route.label;
  if (item.is_form_sla && item.source_entity_type) {
    return item.source_entity_type
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (c) => c.toUpperCase());
  }
  return 'Enquiry';
}

function inboxUrl(item: MyPendingSLAItem): string | null {
  return item.respond_io_id ? `${RESPOND_IO_INBOX_BASE_URL}/${item.respond_io_id}` : null;
}

function dueLabel(due: string | null): { text: string; overdue: boolean } {
  if (!due) return { text: 'No due date', overdue: false };
  const d = new Date(due);
  const overdue = d.getTime() < Date.now();
  return { text: d.toLocaleString(), overdue };
}

export default function MyPendingSLAWidget() {
  const router = useRouter();
  const [items, setItems] = useState<MyPendingSLAItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [resolveTarget, setResolveTarget] = useState<MyPendingSLAItem | null>(null);
  const [resolving, setResolving] = useState(false);
  const [escalateTarget, setEscalateTarget] = useState<MyPendingSLAItem | null>(null);
  const [escalateReason, setEscalateReason] = useState('');
  const [escalating, setEscalating] = useState(false);

  const load = useCallback(() => {
    return getMyPendingSLA()
      .then((data) => setItems(data))
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'));
  }, []);

  useEffect(() => {
    let active = true;
    getMyPendingSLA()
      .then((data) => active && setItems(data))
      .catch((e) => active && setError(e instanceof Error ? e.message : 'Failed to load'));
    return () => {
      active = false;
    };
  }, []);

  // Clicking a row performs its natural action: form rows open the in-system
  // record, conversation rows open the Respond inbox (or the SLA detail when the
  // contact has no resolvable Respond id).
  const doRowAction = useCallback(
    (item: MyPendingSLAItem) => {
      // Form rows with a known record route open the record; otherwise (incl. ticket,
      // and all conversation rows) open the Respond inbox, else the SLA detail.
      const record = entityHref(item);
      if (record) {
        router.push(record);
        return;
      }
      const url = inboxUrl(item);
      if (url) {
        window.open(url, '_blank', 'noopener,noreferrer');
        return;
      }
      router.push(`/sla-management/conversation-sla-tracking/${item.id}`);
    },
    [router],
  );

  const handleResolve = async () => {
    if (!resolveTarget) return;
    setResolving(true);
    try {
      await resolveConversationSLATracking(resolveTarget.id);
      toast.success('Conversation resolved and closed in Respond.');
      setResolveTarget(null);
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to resolve');
    } finally {
      setResolving(false);
    }
  };

  const handleEscalate = async () => {
    if (!escalateTarget) return;
    const reason = escalateReason.trim();
    if (!reason) return;
    setEscalating(true);
    try {
      await escalateConversationSLATracking(escalateTarget.id, reason);
      toast.success('Escalated to the next tier.');
      setEscalateTarget(null);
      setEscalateReason('');
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to escalate');
    } finally {
      setEscalating(false);
    }
  };

  const total = items?.length ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount - 1);
  const pageItems = items ? items.slice(currentPage * PAGE_SIZE, currentPage * PAGE_SIZE + PAGE_SIZE) : [];

  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="mb-3 flex items-center gap-2">
        <Clock className="size-4 text-muted-foreground" />
        <h2 className="text-sm font-semibold">My pending tasks</h2>
        {items !== null && (
          <Badge variant="secondary" className="ml-1">
            {items.length}
          </Badge>
        )}
      </div>

      {error ? (
        <p className="flex items-center gap-2 text-sm text-destructive">
          <AlertCircle className="size-4" /> {error}
        </p>
      ) : items === null ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : items.length === 0 ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <CheckCircle2 className="size-4 text-emerald-600" />
          Nothing pending — you&apos;re all caught up.
        </p>
      ) : (
        <>
          <ul className="divide-y">
            {pageItems.map((item) => {
              const form = isFormTask(item);
              const due = dueLabel(item.due_at);
              const typeLabel = humanizeType(item);
              // Next action follows the SLA config for form rows ("Send for
              // approval", "Approve", "Mark resolved"); conversation rows reply in
              // Respond. No generic "responded/awaiting" wording, no extra line.
              const actionLabel = form ? item.next_action ?? 'Action required' : 'Reply';
              const atMaxTier = item.current_tier >= MAX_TIER;

              return (
                <li key={item.id} className="py-1">
                  <div
                    tabIndex={0}
                    onClick={() => doRowAction(item)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        doRowAction(item);
                      }
                    }}
                    className="-mx-2 cursor-pointer rounded-md px-2 py-2 transition-colors hover:bg-muted/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">
                          {typeLabel}
                          {item.reference ? (
                            <span className="text-muted-foreground"> · {item.reference}</span>
                          ) : null}
                        </p>
                        <p className="truncate text-xs text-muted-foreground">
                          Tier {item.current_tier} · {actionLabel}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-1.5">
                        <span
                          className={`text-xs ${due.overdue ? 'font-medium text-destructive' : 'text-muted-foreground'}`}
                          title={due.text}
                        >
                          {due.overdue ? 'Overdue' : 'Due'}: {due.text}
                        </span>
                        {!entityHref(item) && item.respond_io_id ? (
                          <ExternalLink className="size-3.5 text-muted-foreground" />
                        ) : (
                          <ChevronRight className="size-4 text-muted-foreground" />
                        )}
                      </div>
                    </div>

                    {/* Conversation rows carry inline actions; clicks here must not
                        trigger the row's open action. Form rows have none. */}
                    {!form && (
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-7"
                          disabled={atMaxTier}
                          title={atMaxTier ? 'Already at the maximum tier' : 'Escalate to the next tier'}
                          onClick={(e) => {
                            e.stopPropagation();
                            setEscalateReason('');
                            setEscalateTarget(item);
                          }}
                        >
                          <TrendingUp className="size-3.5" />
                          Escalate
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7"
                          onClick={(e) => {
                            e.stopPropagation();
                            setResolveTarget(item);
                          }}
                        >
                          <CheckCircle2 className="size-3.5" />
                          Resolve
                        </Button>
                      </div>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
          {total > PAGE_SIZE && (
            <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
              <span>
                {currentPage * PAGE_SIZE + 1}–{Math.min((currentPage + 1) * PAGE_SIZE, total)} of {total}
              </span>
              <div className="flex items-center gap-1">
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  className="size-7"
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={currentPage === 0}
                  aria-label="Previous page"
                >
                  <ChevronLeft className="size-4" />
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  className="size-7"
                  onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
                  disabled={currentPage >= pageCount - 1}
                  aria-label="Next page"
                >
                  <ChevronRight className="size-4" />
                </Button>
              </div>
            </div>
          )}
        </>
      )}

      <AlertDialog open={!!resolveTarget} onOpenChange={(o) => !o && setResolveTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Mark as resolved</AlertDialogTitle>
            <AlertDialogDescription>
              This stops the SLA clock and closes the conversation in Respond. This action cannot be
              undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={resolving}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={(e) => { e.preventDefault(); void handleResolve(); }} disabled={resolving}>
              {resolving ? 'Resolving…' : 'Confirm'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Dialog
        open={!!escalateTarget}
        onOpenChange={(o) => {
          if (!o) {
            setEscalateTarget(null);
            setEscalateReason('');
          }
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Escalate to tier {(escalateTarget?.current_tier ?? 1) + 1}</DialogTitle>
          </DialogHeader>
          <div className="space-y-2 py-1">
            <Label htmlFor="pending-escalate-reason">Reason</Label>
            <Input
              id="pending-escalate-reason"
              placeholder="Why escalate now?"
              value={escalateReason}
              onChange={(e) => setEscalateReason(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && escalateReason.trim() && !escalating) {
                  e.preventDefault();
                  void handleEscalate();
                }
              }}
              autoFocus
            />
            <p className="text-xs text-muted-foreground">
              Moves this conversation to the next tier and reassigns per policy. The new assignee is
              notified.
            </p>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setEscalateTarget(null);
                setEscalateReason('');
              }}
              disabled={escalating}
            >
              Cancel
            </Button>
            <Button onClick={() => void handleEscalate()} disabled={escalating || !escalateReason.trim()}>
              {escalating ? 'Escalating…' : 'Escalate'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
