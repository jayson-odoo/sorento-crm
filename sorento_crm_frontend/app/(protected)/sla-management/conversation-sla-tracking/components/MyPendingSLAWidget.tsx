'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { AlertCircle, CheckCircle2, Clock } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
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

function hrefFor(item: MyPendingSLAItem): string | null {
  if (!item.source_entity_type || !item.source_entity_id) return null;
  const route = ENTITY_ROUTES[item.source_entity_type];
  return route ? `${route.base}/${item.source_entity_id}` : null;
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

  useEffect(() => {
    let active = true;
    getMyPendingSLA()
      .then((data) => active && setItems(data))
      .catch((e) => active && setError(e instanceof Error ? e.message : 'Failed to load'));
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="mb-3 flex items-center gap-2">
        <Clock className="size-4 text-muted-foreground" />
        <h2 className="text-sm font-semibold">My pending SLAs</h2>
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
        <ul className="divide-y">
          {items.map((item) => {
            const href = hrefFor(item);
            const due = dueLabel(item.due_at);
            const typeLabel =
              (item.source_entity_type && ENTITY_ROUTES[item.source_entity_type]?.label) ||
              item.source_entity_type ||
              'SLA';
            const row = (
              <div className="flex items-center justify-between gap-2 py-2">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{typeLabel}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {item.policy_name ?? 'SLA'} · Tier {item.current_tier}
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
                {href ? (
                  <Link href={href} className="block hover:bg-muted/50">
                    {row}
                  </Link>
                ) : (
                  row
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
