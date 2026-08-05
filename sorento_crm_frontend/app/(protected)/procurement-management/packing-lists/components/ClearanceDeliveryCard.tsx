'use client';

import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDate } from '@/lib/helpers';
import { useClearanceCheckpoints } from '../hooks/usePackingLists';
import type { ClearanceCheckpoint } from '../services/packingListService';
import type { PackingListDetail } from '../types/packingList.types';

/**
 * Clearance and delivery for one container, as a checkpoint timeline.
 *
 * **A container does not walk a straight line, and this must not pretend it does.**
 * The real workbook has containers with a gatepass and no inspection, an ETA delay
 * and no ETA, a collection with no warehouse arrival. So every checkpoint is shown
 * and each is independently reached or not - there is no single "current status",
 * no assumption that reaching a later step completed the earlier ones, and no
 * progress bar implying a percentage that would be a fiction.
 *
 * The checkpoint list is NOT hardcoded here. Labels, captions, grouping, order,
 * colour and visibility come from `statuses` under entity_type
 * `inbound_shipment` and are edited in System Management -> Status Graphs. Adding,
 * renaming, reordering or hiding a checkpoint is an admin action, not a deploy.
 *
 * Rendered ALWAYS, even with nothing imported yet - per the CRUD UX standard the
 * section never disappears, it shows an explicit empty state with the next step.
 */

type DateKey = keyof PackingListDetail;

/**
 * Present on the sheet but effectively unmaintained - fill rates across the 407
 * real containers are 6 / 4 / 4 / 4. Deliberately NOT checkpoints: four
 * permanently grey dots would drown the eleven that matter. Shown below the
 * timeline so an importer can still find them.
 */
const RARELY_USED: Array<{ key: DateKey; label: string; source: string }> = [
  { key: 'ata_date', label: 'ATA', source: 'superseded by ETA Delay' },
  { key: 'ori_doc_received_date', label: 'Ori Doc Received', source: 'China agent' },
  { key: 'k1_submission_date', label: 'K1 Submission', source: 'customs declaration' },
  { key: 'yard_arrival_date', label: 'Yard Arrival', source: '48h after gatepass' },
];

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

const GROUP_LABELS: Record<string, string> = {
  origin: 'Origin',
  sea: 'Sea',
  clearance: 'Clearance',
  delivery: 'Delivery',
};

function asText(value: unknown): string | null {
  if (value === null || value === undefined || value === '') return null;
  return String(value);
}

function CheckpointRow({
  checkpoint,
  packingList,
  isLast,
}: {
  checkpoint: ClearanceCheckpoint;
  packingList: PackingListDetail;
  isLast: boolean;
}) {
  const raw = asText(packingList[checkpoint.field as DateKey]);
  const reached = raw !== null;
  // The admin's colour, used only once the checkpoint is actually reached. An
  // unreached dot stays neutral so the eye lands on what has happened.
  const dotColor = reached ? checkpoint.color ?? undefined : undefined;

  return (
    <li className="relative flex gap-3 pb-5 last:pb-0">
      {/* The connector, drawn behind the dot and stopped on the last item. */}
      {!isLast && (
        <span
          aria-hidden
          className="absolute start-[7px] top-4 h-full w-px bg-border"
        />
      )}
      <span
        aria-hidden
        className={`relative mt-1 size-3.5 shrink-0 rounded-full border-2 ${
          reached ? 'border-transparent' : 'border-muted-foreground/30 bg-background'
        }`}
        style={dotColor ? { backgroundColor: dotColor } : undefined}
      />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
          <p
            className={`text-sm ${reached ? 'font-medium' : 'text-muted-foreground'}`}
          >
            {checkpoint.label}
          </p>
          <p
            className={`shrink-0 text-sm tabular-nums ${
              reached ? 'font-medium' : 'text-muted-foreground'
            }`}
          >
            {reached ? formatDate(new Date(raw)) : 'Not reached'}
          </p>
        </div>
        {checkpoint.caption && (
          <p className="text-xs text-muted-foreground">{checkpoint.caption}</p>
        )}
      </div>
    </li>
  );
}

export default function ClearanceDeliveryCard({
  packingList,
}: {
  packingList: PackingListDetail;
}) {
  const { data: checkpoints, isLoading, isError } = useClearanceCheckpoints();

  const list = checkpoints ?? [];
  const reachedCount = list.filter(
    (c) => asText(packingList[c.field as DateKey]) !== null,
  ).length;
  const hasAnyDate =
    reachedCount > 0 ||
    RARELY_USED.some((m) => asText(packingList[m.key]) !== null);

  const parties = PARTY_FIELDS.map((f) => ({
    ...f,
    value: asText(packingList[f.key]),
  })).filter((f) => f.value !== null);
  const sourceSheet = asText(packingList.source_sheet);

  // Group in the order the checkpoints arrive, so an admin reordering them
  // reorders the groups too rather than fighting a hardcoded sequence.
  const groups: Array<{ key: string; items: ClearanceCheckpoint[] }> = [];
  for (const checkpoint of list) {
    const key = checkpoint.group ?? 'other';
    const last = groups[groups.length - 1];
    if (last && last.key === key) last.items.push(checkpoint);
    else groups.push({ key, items: [checkpoint] });
  }

  return (
    <Card className="lg:col-span-3">
      {/* flex-col must pin items-start, or the title centres itself at phone width. */}
      <CardHeader className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
        <CardTitle className="min-w-0 break-words">Clearance &amp; Delivery</CardTitle>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {list.length > 0 && (
            <Badge variant="outline">
              {reachedCount} of {list.length} reached
            </Badge>
          )}
          {sourceSheet && <Badge variant="secondary">Sheet: {sourceSheet}</Badge>}
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="flex gap-3">
                <Skeleton className="mt-1 size-3.5 rounded-full" />
                <div className="flex-1 space-y-1">
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-3 w-48" />
                </div>
              </div>
            ))}
          </div>
        ) : isError || list.length === 0 ? (
          <div className="rounded-lg border border-dashed p-6 text-center">
            <p className="text-sm font-medium">
              {isError ? 'Could not load the checkpoints' : 'No checkpoints configured'}
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              The clearance timeline is configured under System Management, so the
              steps and their names can be changed without a release.
            </p>
            <Link
              href="/system-management/status-graphs"
              className="mt-3 inline-block text-sm font-medium text-primary hover:underline"
            >
              Open Status Graphs
            </Link>
          </div>
        ) : !hasAnyDate ? (
          <div className="rounded-lg border border-dashed p-6 text-center">
            <p className="text-sm font-medium">No container status imported yet</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Clearance dates arrive with the Container Status workbook. Import it and
              this container will fill in automatically, matched on its container
              number.
            </p>
            {/* Lands on the upload dialog itself, not just the list - the list page
                opens it from ?import=container-status. */}
            <Link
              href="/procurement-management/packing-lists?import=container-status"
              className="mt-3 inline-block text-sm font-medium text-primary hover:underline"
            >
              Import Container Status workbook
            </Link>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 gap-x-8 gap-y-6 md:grid-cols-2 xl:grid-cols-4">
              {groups.map((group) => (
                <div key={group.key}>
                  <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    {GROUP_LABELS[group.key] ?? group.key}
                  </p>
                  <ol className="relative">
                    {group.items.map((checkpoint, index) => (
                      <CheckpointRow
                        key={checkpoint.field}
                        checkpoint={checkpoint}
                        packingList={packingList}
                        isLast={index === group.items.length - 1}
                      />
                    ))}
                  </ol>
                </div>
              ))}
            </div>

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

            <div className="border-t pt-4">
              <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Also on the sheet, rarely filled
              </p>
              <div className="grid grid-cols-1 gap-x-8 sm:grid-cols-2 lg:grid-cols-4">
                {RARELY_USED.map((m) => {
                  const raw = asText(packingList[m.key]);
                  return (
                    <div
                      key={String(m.key)}
                      className="flex items-baseline justify-between gap-3 py-1.5"
                    >
                      <div className="min-w-0">
                        <p className="text-sm text-muted-foreground">{m.label}</p>
                        <p
                          className="truncate text-xs text-muted-foreground"
                          title={m.source}
                        >
                          {m.source}
                        </p>
                      </div>
                      <p
                        className={`shrink-0 text-sm tabular-nums ${
                          raw ? 'font-medium' : 'text-muted-foreground'
                        }`}
                      >
                        {raw ? formatDate(new Date(raw)) : 'Not reached'}
                      </p>
                    </div>
                  );
                })}
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
