'use client';

/**
 * Prev/next record navigation for a price tag request (D50).
 *
 * List mode rather than a neighbours endpoint: the backend answers this
 * resource as one flat list that the service already pages on the client, so
 * the set the chevrons walk is a call the app makes anyway. The chevrons were
 * previously wired to a hard-coded null prev and null next, which made them
 * permanently dead.
 */

import { useEffect, useState } from 'react';
import RecordNavigation from '@/components/common/RecordNavigation';
import {
  listPriceTagRequests,
  type PriceTagRequestSummary,
} from '../../services/priceTagRequestService';

interface Props {
  requestId: string;
  className?: string;
}

export default function PriceTagRequestNavigation({ requestId, className }: Props) {
  const [items, setItems] = useState<PriceTagRequestSummary[]>([]);

  useEffect(() => {
    let cancelled = false;
    listPriceTagRequests({ page: 1, limit: 500, sort: 'created_at', dir: 'desc' })
      .then((result) => {
        if (!cancelled) setItems(result.data);
      })
      .catch(() => {
        // A list that will not load leaves the chevrons disabled. It must not
        // stop the record being read.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <RecordNavigation
      basePath="/dealer-kit/price-tag-requests"
      currentId={requestId}
      items={items}
      ariaLabel="price tag request"
      className={className}
    />
  );
}
