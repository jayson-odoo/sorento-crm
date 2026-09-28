'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { MessageSquareText } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { portalBase } from '../lib/portal-paths';
import { listCustomerAsks } from '../lib/customer-asks-service';

/**
 * Chatbot stock ask v2 S6 (AC-SA606): the way into Customer asks, shown only to a contact
 * linked to a sales agent. The open-count probe doubles as the gate - its 403 hides the link.
 */
export function CustomerAsksLink({ slug }: { slug?: string | null }) {
  const [openCount, setOpenCount] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    listCustomerAsks({ page: 1, limit: 1, state: 'open' })
      .then((page) => {
        if (!cancelled) setOpenCount(page.pagination?.total ?? 0);
      })
      .catch(() => {
        if (!cancelled) setOpenCount(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (openCount === null) return null;
  return (
    <Button asChild variant="outline" className="h-11 w-full justify-between">
      <Link href={`${portalBase(slug)}/customer_asks`}>
        <span className="flex items-center gap-2">
          <MessageSquareText className="size-4" />
          Customer asks
        </span>
        <Badge variant="secondary" className="px-1.5 py-0 text-xs" aria-label={`${openCount} open`}>
          {openCount}
        </Badge>
      </Link>
    </Button>
  );
}
