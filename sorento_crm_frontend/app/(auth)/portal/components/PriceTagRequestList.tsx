'use client';

/**
 * Portal price tag request list - shows all requests for the current contact.
 *
 * Phase 1: mock data. Renders as mobile-first card list (consistent with the
 * existing portal landing page pattern).
 */

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeft, FileText, Plus } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  priceTagStatusLabel,
  priceTagStatusPillClass,
} from '@/lib/price-tag-status';
import { portalBase, portalNewPath, portalDetailPath } from '../lib/portal-paths';
import { listRequests, type PriceTagRequestSummary } from '../lib/price-tag-request-service';

interface Props {
  slug?: string;
}

export function PriceTagRequestList({ slug }: Props) {
  const router = useRouter();
  const [requests, setRequests] = useState<PriceTagRequestSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    listRequests()
      .then((data) => {
        if (!cancelled) setRequests(data);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="w-full max-w-2xl mx-auto px-3 pt-4 pb-8 space-y-4">
      <div className="flex items-center justify-between">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => router.push(portalBase(slug))}
        >
          <ArrowLeft className="size-4 mr-1" /> Back
        </Button>
        <Button
          size="sm"
          onClick={() => router.push(portalNewPath('price_tag_request', slug))}
        >
          <Plus className="size-4 mr-1" /> New Request
        </Button>
      </div>

      <h1 className="text-lg font-semibold">Price Tag Requests</h1>

      {loading && (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      )}

      {!loading && requests.length === 0 && (
        <Card>
          <CardContent className="py-8 text-center">
            <FileText className="size-10 mx-auto text-muted-foreground mb-3" />
            <p className="text-sm text-muted-foreground">
              No price tag requests yet.
            </p>
            <Button
              size="sm"
              className="mt-3"
              onClick={() =>
                router.push(portalNewPath('price_tag_request', slug))
              }
            >
              <Plus className="size-4 mr-1" /> Create your first request
            </Button>
          </CardContent>
        </Card>
      )}

      {!loading &&
        requests.map((req) => (
          <Card
            key={req.id}
            className="cursor-pointer hover:bg-accent/50 transition-colors"
            onClick={() =>
              router.push(
                portalDetailPath('price_tag_request', req.id, slug),
              )
            }
          >
            <CardContent className="py-3 px-4">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-sm truncate" title={req.doc_number}>
                      {req.doc_number}
                    </span>
                    <span
                      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${priceTagStatusPillClass(req.status)}`}
                    >
                      {priceTagStatusLabel(req.status)}
                    </span>
                  </div>
                  <p
                    className="text-sm text-muted-foreground mt-0.5 truncate"
                    title={req.debtor_name}
                  >
                    {req.debtor_name}
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap gap-x-4 gap-y-0.5 mt-2 text-xs text-muted-foreground">
                <span>Deadline: {req.needed_by_date}</span>
                <span>
                  {req.line_count} {req.line_count === 1 ? 'line' : 'lines'}
                </span>
                <span>
                  Created:{' '}
                  {new Date(req.created_at).toLocaleDateString()}
                </span>
              </div>
            </CardContent>
          </Card>
        ))}
    </div>
  );
}
