'use client';

import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import type { GroupingOrigin, SalesOrderStatus } from '../../_shared/types/projectSalesOrder.types';

/**
 * Sales order statuses are new words for colours the shared palette already owns, so they
 * are mapped onto its existing keys rather than given a palette of their own: blocked reads
 * like a refusal, ready like an approval, published like a finished job.
 */
const PALETTE_KEY: Record<SalesOrderStatus, string> = {
  draft: 'draft',
  blocked: 'rejected',
  ready: 'approved',
  published: 'processed_by_cs',
  amended: 'updated',
};

const STATUS_LABEL: Record<SalesOrderStatus, string> = {
  draft: 'Draft',
  blocked: 'Blocked',
  ready: 'Ready',
  published: 'Published',
  amended: 'Amended',
};

export function SalesOrderStatusPill({ status }: { status: SalesOrderStatus }) {
  return (
    <span className={`${STATUS_PILL_BASE} ${statusPillClass(PALETTE_KEY[status] ?? status)}`}>
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

/** Where the split came from, said in the words a reviewer needs to judge it. */
export const GROUPING_ORIGIN_LABEL: Record<GroupingOrigin, string> = {
  area: 'Split by schedule area',
  learned: 'Split as last time for this customer',
  manual: 'Split by hand',
  subset: 'Product subset, no area',
};

export function GroupingOriginNote({ origin }: { origin: GroupingOrigin }) {
  return (
    <span
      className="block truncate text-xs text-muted-foreground"
      title={GROUPING_ORIGIN_LABEL[origin] ?? origin}
    >
      {GROUPING_ORIGIN_LABEL[origin] ?? origin}
    </span>
  );
}
