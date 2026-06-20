'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { toast } from 'sonner';
import {
  AlertCircle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  ExternalLink,
  FileText,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
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

const PAGE_SIZE = 5;
import {
  getMyPendingSLA,
  resolveConversationSLATracking,
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

/** A row is a form-SLA task when it has a known source entity; otherwise it is a
 * conversation-SLA task handled in the Respond inbox. */
function isFormTask(item: MyPendingSLAItem): boolean {
  return !!(item.source_entity_type && item.source_entity_id && ENTITY_ROUTES[item.source_entity_type]);
}

function entityHref(item: MyPendingSLAItem): string {
  const route = ENTITY_ROUTES[item.source_entity_type ?? ''];
  if (route && item.source_entity_id) return `${route.base}/${item.source_entity_id}`;
  return `/sla-management/conversation-sla-tracking/${item.id}`;
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
  const [items, setItems] = useState<MyPendingSLAItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [resolveTarget, setResolveTarget] = useState<MyPendingSLAItem | null>(null);
  const [resolving, setResolving] = useState(false);

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
              const typeLabel =
                (item.source_entity_type && ENTITY_ROUTES[item.source_entity_type]?.label) ||
                (form ? item.source_entity_type : 'Enquiry') ||
                'Enquiry';
              // Next action follows the SLA config for form rows ("Send for
              // approval", "Approve", "Mark resolved"); conversation rows reply in
              // Respond. No generic "responded/awaiting" wording, no extra line.
              const actionLabel = form
                ? item.next_action ?? 'Action required'
                : 'Reply';
              const url = inboxUrl(item);

              return (
                <li key={item.id} className="py-2">
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
                    <span
                      className={`shrink-0 text-xs ${due.overdue ? 'font-medium text-destructive' : 'text-muted-foreground'}`}
                      title={due.text}
                    >
                      {due.overdue ? 'Overdue' : 'Due'}: {due.text}
                    </span>
                  </div>

                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    {form ? (
                      <Button asChild size="sm" variant="outline" className="h-7">
                        <Link href={entityHref(item)}>
                          <FileText className="size-3.5" />
                          Open record
                        </Link>
                      </Button>
                    ) : (
                      <>
                        {url ? (
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-7"
                            onClick={() => window.open(url, '_blank', 'noopener,noreferrer')}
                          >
                            <ExternalLink className="size-3.5" />
                            Open in Respond
                          </Button>
                        ) : (
                          <Button asChild size="sm" variant="outline" className="h-7">
                            <Link href={`/sla-management/conversation-sla-tracking/${item.id}`}>
                              Open details
                            </Link>
                          </Button>
                        )}
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7"
                          onClick={() => setResolveTarget(item)}
                        >
                          <CheckCircle2 className="size-3.5" />
                          Resolve
                        </Button>
                      </>
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
    </div>
  );
}
