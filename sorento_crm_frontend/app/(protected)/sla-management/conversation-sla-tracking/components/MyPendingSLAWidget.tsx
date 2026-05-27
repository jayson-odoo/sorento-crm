'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { AlertCircle, CheckCircle2, ChevronLeft, ChevronRight, Clock } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

const PAGE_SIZE = 5;
import {
  getMyPendingSLA,
  type MyPendingSLAItem,
} from '../services/conversationSLATrackingService';

const ENTITY_ROUTES: Record<string, { base: string; label: string }> = {
  stock_inquiry: { base: '/procurement-management/stock-inquiries', label: 'Stock inquiry' },
  complaint: { base: '/complaint-management/complaints', label: 'Complaint' },
  purchase_request: { base: '/procurement-management/purchase-requests', label: 'Purchase request' },
  sponsorship_form: { base: '/procurement-management/purchase-requests', label: 'Sponsorship form' },
};

function hrefFor(item: MyPendingSLAItem): string {
  // Form trackers (complaint / stock_inquiry / purchase_request / sponsorship)
  // link to their record page; everything else (ticket / conversation SLAs with
  // no source entity) falls back to the SLA tracking detail page.
  if (item.source_entity_type && item.source_entity_id) {
    const route = ENTITY_ROUTES[item.source_entity_type];
    if (route) return `${route.base}/${item.source_entity_id}`;
  }
  return `/sla-management/conversation-sla-tracking/${item.id}`;
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

  useEffect(() => {
    let active = true;
    getMyPendingSLA()
      .then((data) => active && setItems(data))
      .catch((e) => active && setError(e instanceof Error ? e.message : 'Failed to load'));
    return () => {
      active = false;
    };
  }, []);

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
            const href = hrefFor(item);
            const due = dueLabel(item.due_at);
            const typeLabel =
              (item.source_entity_type && ENTITY_ROUTES[item.source_entity_type]?.label) ||
              item.source_entity_type ||
              'Enquiries';
            const row = (
              <div className="flex items-center justify-between gap-2 py-2">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    {typeLabel}
                    {item.reference ? <span className="text-muted-foreground"> · {item.reference}</span> : null}
                  </p>
                  <p className="truncate text-xs text-muted-foreground">
                    Tier {item.current_tier}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {item.is_responded ? (
                    <Badge variant="secondary">Responded</Badge>
                  ) : null}
                  <span
                    className={`text-xs ${due.overdue ? 'font-medium text-destructive' : 'text-muted-foreground'}`}
                    title={due.text}
                  >
                    {due.overdue ? 'Overdue' : 'Due'}: {due.text}
                  </span>
                </div>
              </div>
            );
            return (
              <li key={item.id}>
                <Link href={href} className="block hover:bg-muted/50">
                  {row}
                </Link>
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
    </div>
  );
}
