'use client';

import { Badge } from '@/components/ui/badge';
import { Lock } from 'lucide-react';

/**
 * Uniform provenance badge for AutoCount-mirrored records. Shared so the
 * "this is read-only synced data" signal renders identically across every
 * mirror list and detail page (Master Data, Order Mgmt, Procurement, Inventory)
 * and cannot drift per feature.
 */
export function AutoCountSourceBadge({ source }: { source?: 'autocount' | 'manual' }) {
  if (source === 'manual') {
    return (
      <Badge variant="secondary" appearance="outline">
        Manual
      </Badge>
    );
  }
  return (
    <Badge variant="info" appearance="ghost" title="Synced from AutoCount — read-only">
      <Lock className="size-3" />
      AutoCount
    </Badge>
  );
}
