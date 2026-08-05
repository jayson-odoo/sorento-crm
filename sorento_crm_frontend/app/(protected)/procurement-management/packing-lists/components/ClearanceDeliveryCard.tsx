'use client';

import Link from 'next/link';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDate } from '@/lib/helpers';
import { useClearanceCheckpoints } from '../hooks/usePackingLists';
import type { ClearanceCheckpoint } from '../services/packingListService';
import type { PackingListDetail } from '../types/packingList.types';

/**
 * Where a container actually got to, as one vertical timeline.
 *
 * **Only checkpoints that happened are shown.** A container does not walk a
 * straight line - the real workbook has containers with a gatepass and no
 * inspection, an ETA delay and no ETA - so an unreached checkpoint is not a step
 * "pending", it is simply a thing that has not been recorded. Rendering eleven
 * rows where five are dates and six say "Not reached" buries the five that matter.
 * The count in the header is what tells you the rest exist.
 *
 * **One flat ordered list, no groups.** An earlier version grouped these under
 * ORIGIN / SEA / CLEARANCE / DELIVERY, but those four names were a hardcoded map
 * in this file: an admin adding a checkpoint had nowhere to put it, and renaming a
 * group meant a release. Order alone carries the same meaning (D35).
 *
 * Labels, captions, order, colour and visibility all come from `statuses` under
 * entity_type `inbound_shipment`, edited in System Management -> Status Graphs.
 */

type DateKey = keyof PackingListDetail;

const PARTY_FIELDS: Array<{ key: DateKey; label: string }> = [
  { key: 'liner_code', label: 'Liner' },
  { key: 'china_forwarder', label: 'China Forwarder' },
  { key: 'malaysia_forwarder', label: 'Malaysia Forwarder' },
  { key: 'consignee', label: 'Consignee' },
  { key: 'loc', label: 'Location' },
  { key: 'free_days_available', label: 'Free Days' },
  { key: 'delivery_warehouse', label: 'Delivery Warehouse' },
  { key: 'coa_permit_no', label: 'COA Permit No' },
];

function asText(value: unknown): string | null {
  if (value === null || value === undefined || value === '') return null;
  return String(value);
}

function EmptyState({
  title,
  body,
  href,
  cta,
}: {
  title: string;
  body: string;
  href: string;
  cta: string;
}) {
  return (
    <div className="rounded-lg border border-dashed p-6 text-center">
      <p className="text-sm font-medium">{title}</p>
      <p className="mt-1 text-sm text-muted-foreground">{body}</p>
      <Link
        href={href}
        className="mt-3 inline-block text-sm font-medium text-primary hover:underline"
      >
        {cta}
      </Link>
    </div>
  );
}

export default function ClearanceDeliveryCard({
  packingList,
}: {
  packingList: PackingListDetail;
}) {
  const { data: checkpoints, isLoading, isError } = useClearanceCheckpoints();

  const configured = checkpoints ?? [];
  const reached: Array<ClearanceCheckpoint & { date: string }> = configured
    .map((c) => ({ ...c, date: asText(packingList[c.field as DateKey]) }))
    .filter((c): c is ClearanceCheckpoint & { date: string } => c.date !== null);

  const parties = PARTY_FIELDS.map((f) => ({
    ...f,
    value: asText(packingList[f.key]),
  })).filter((f) => f.value !== null);
  const sourceSheet = asText(packingList.source_sheet);

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="flex gap-3">
            <Skeleton className="mt-1 size-3.5 rounded-full" />
            <div className="flex-1 space-y-1">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-3 w-48" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (isError || configured.length === 0) {
    return (
      <EmptyState
        title={isError ? 'Could not load the checkpoints' : 'No checkpoints configured'}
        body="The clearance timeline is configured under System Management, so the steps and their names can be changed without a release."
        href="/system-management/status-graphs"
        cta="Open Status Graphs"
      />
    );
  }

  if (reached.length === 0) {
    return (
      <EmptyState
        title="No container status imported yet"
        body="Clearance dates arrive with the Container Status workbook. Import it and this container will fill in automatically, matched on its container number."
        href="/procurement-management/packing-lists?import=container-status"
        cta="Import Container Status workbook"
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">
          {reached.length} of {configured.length} checkpoints reached
        </Badge>
        {sourceSheet && <Badge variant="secondary">Sheet: {sourceSheet}</Badge>}
      </div>

      <ol className="relative">
        {reached.map((checkpoint, index) => (
          <li key={checkpoint.field} className="relative flex gap-4 pb-6 last:pb-0">
            {/* Connector, drawn behind the dot and stopped after the last entry. */}
            {index < reached.length - 1 && (
              <span
                aria-hidden
                className="absolute start-[7px] top-4 h-full w-px bg-border"
              />
            )}
            <span
              aria-hidden
              className="relative mt-1 size-3.5 shrink-0 rounded-full"
              style={{ backgroundColor: checkpoint.color ?? undefined }}
            />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5">
                <p className="text-sm font-medium">{checkpoint.label}</p>
                <p className="shrink-0 text-sm font-medium tabular-nums">
                  {formatDate(new Date(checkpoint.date))}
                </p>
              </div>
              {checkpoint.caption && (
                <p className="text-xs text-muted-foreground">{checkpoint.caption}</p>
              )}
            </div>
          </li>
        ))}
      </ol>

      <div className="border-t pt-4">
        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Parties &amp; references
        </p>
        {parties.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No liner or forwarder recorded for this container yet.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {parties.map((f) => (
              <div key={String(f.key)} className="min-w-0">
                <p className="text-sm text-muted-foreground">{f.label}</p>
                <p className="truncate font-medium" title={f.value ?? undefined}>
                  {f.value}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
