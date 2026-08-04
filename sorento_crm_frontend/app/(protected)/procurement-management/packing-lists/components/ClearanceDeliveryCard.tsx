'use client';

import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { formatDate } from '@/lib/helpers';
import type { PackingListDetail } from '../types/packingList.types';

/**
 * Clearance and delivery milestones for one container.
 *
 * Rendered ALWAYS, even with nothing imported yet - per the CRUD UX standard the
 * section never disappears, it shows an explicit empty state with the next step.
 *
 * The chain order is the real one from the workbook, and the target intervals in the
 * captions are CIDB's statutory ones (COA is issued within 3 working days of port
 * verification), not invented SLAs.
 */

type DateKey = keyof PackingListDetail;

interface Milestone {
  key: DateKey;
  label: string;
  /** Who supplies this date in practice. Shown as a muted caption. */
  source: string;
}

const ORIGIN: Milestone[] = [
  { key: 'loading_date', label: 'Loading', source: '2-4 days before ETD' },
  { key: 'etc_date', label: 'ETC', source: 'China forwarder' },
  { key: 'etd_date', label: 'ETD', source: 'China forwarder' },
];

const SEA: Milestone[] = [
  { key: 'eta_date', label: 'ETA', source: 'Liner, first published' },
  { key: 'eta_delay_date', label: 'ETA Delay', source: 'Liner, revised - the accurate one' },
];

const CLEARANCE: Milestone[] = [
  { key: 'inspection_date', label: 'Inspection', source: 'CIDB officer at port' },
  { key: 'approval_date', label: 'Approval (COA)', source: 'CIDB, within 3 working days of inspection' },
  { key: 'gatepass_date', label: 'Gatepass', source: 'Malaysia forwarder, same day as duty paid' },
];

const DELIVERY: Milestone[] = [
  { key: 'warehouse_arrival_date', label: 'Warehouse Arrival', source: 'Yard' },
  { key: 'informed_collection_date', label: 'Informed Collection', source: '48h after gatepass' },
  { key: 'collection_date', label: 'Collection', source: 'Within 6 days of exit gate' },
];

/**
 * Present on the sheet but effectively unmaintained - fill rates across 411 rows are
 * 6 / 4 / 4 / 4. Shown so an importer can find them, kept visually secondary so nobody
 * mistakes them for part of the live chain.
 */
const RARELY_USED: Milestone[] = [
  { key: 'ata_date', label: 'ATA', source: 'superseded by ETA Delay' },
  { key: 'ori_doc_received_date', label: 'Ori Doc Received', source: 'China agent' },
  { key: 'k1_submission_date', label: 'K1 Submission', source: 'customs declaration' },
  { key: 'yard_arrival_date', label: 'Yard Arrival', source: '48h after gatepass' },
];

const ALL_DATE_KEYS: DateKey[] = [
  ...ORIGIN, ...SEA, ...CLEARANCE, ...DELIVERY, ...RARELY_USED,
].map((m) => m.key);

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

function MilestoneRow({
  milestone,
  packingList,
  muted = false,
}: {
  milestone: Milestone;
  packingList: PackingListDetail;
  muted?: boolean;
}) {
  const raw = asText(packingList[milestone.key]);
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5">
      <div className="min-w-0">
        <p className={`text-sm ${muted ? 'text-muted-foreground' : 'font-medium'}`}>
          {milestone.label}
        </p>
        <p className="text-xs text-muted-foreground truncate" title={milestone.source}>
          {milestone.source}
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
}

function MilestoneGroup({
  title,
  milestones,
  packingList,
  muted = false,
}: {
  title: string;
  milestones: Milestone[];
  packingList: PackingListDetail;
  muted?: boolean;
}) {
  return (
    <div>
      <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {title}
      </p>
      <div className="divide-y">
        {milestones.map((m) => (
          <MilestoneRow key={String(m.key)} milestone={m} packingList={packingList} muted={muted} />
        ))}
      </div>
    </div>
  );
}

export default function ClearanceDeliveryCard({
  packingList,
}: {
  packingList: PackingListDetail;
}) {
  const hasAnyDate = ALL_DATE_KEYS.some((k) => asText(packingList[k]) !== null);
  const parties = PARTY_FIELDS.map((f) => ({ ...f, value: asText(packingList[f.key]) })).filter(
    (f) => f.value !== null,
  );
  const sourceSheet = asText(packingList.source_sheet);

  return (
    <Card className="lg:col-span-3">
      {/* flex-col must pin items-start, or the title centres itself at phone width. */}
      <CardHeader className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
        <CardTitle className="min-w-0 break-words">Clearance &amp; Delivery</CardTitle>
        {sourceSheet && (
          <Badge variant="secondary" className="shrink-0">
            Sheet: {sourceSheet}
          </Badge>
        )}
      </CardHeader>
      <CardContent className="space-y-6">
        {!hasAnyDate ? (
          <div className="rounded-lg border border-dashed p-6 text-center">
            <p className="text-sm font-medium">No container status imported yet</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Clearance dates arrive with the Container Status workbook. Upload it and this
              container will fill in automatically, matched on its container number.
            </p>
            <Link
              href="/resource-management/attachment-directories"
              className="mt-3 inline-block text-sm font-medium text-primary hover:underline"
            >
              Go to Resource Management &rarr; Files
            </Link>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-1 gap-x-8 gap-y-6 md:grid-cols-2 xl:grid-cols-4">
              <MilestoneGroup title="Origin" milestones={ORIGIN} packingList={packingList} />
              <MilestoneGroup title="Sea" milestones={SEA} packingList={packingList} />
              <MilestoneGroup title="Clearance" milestones={CLEARANCE} packingList={packingList} />
              <MilestoneGroup title="Delivery" milestones={DELIVERY} packingList={packingList} />
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
                {RARELY_USED.map((m) => (
                  <MilestoneRow key={String(m.key)} milestone={m} packingList={packingList} muted />
                ))}
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
