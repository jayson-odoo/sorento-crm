'use client';

/**
 * The design, at the top of the CRM Request tab (r9 S1/D3).
 *
 * Marketing used to have to open the designer to see what a request looks like,
 * which meant loading the whole Konva editor to answer "is this the one the
 * salesperson is asking about". The same `DesignViewer` the portal reads is the
 * answer, drawing the DRAFT (B1) so the office sees its own work in progress.
 */

import { useEffect, useState } from 'react';

import DesignViewer from '@/components/dealer-kit/DesignViewer';
import { getRequestDesignPayload } from '../../services/priceTagRequestService';
import type { TagSheetDesignPayload } from '@/lib/dealer-kit/design-payload';

interface Props {
  requestId: string;
  docNumber: string;
}

export default function RequestDesignSection({ requestId, docNumber }: Props) {
  const [payload, setPayload] = useState<TagSheetDesignPayload | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getRequestDesignPayload(requestId)
      .then((data) => {
        if (!cancelled) setPayload(data);
      })
      .catch(() => {
        // No design yet, or the fetch failed - the empty state is the right
        // answer either way, and the page has nothing else to say about it.
        if (!cancelled) setPayload(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [requestId]);

  return (
    <DesignViewer
      docNumber={docNumber}
      payload={payload}
      loading={loading}
      emptyMessage="No design yet"
      emptyHint="Claim the request and open the designer to draw the tags."
    />
  );
}
