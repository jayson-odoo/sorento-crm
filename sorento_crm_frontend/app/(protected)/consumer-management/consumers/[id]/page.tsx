'use client';

/**
 * Consumer 360 - everything the ledger holds about one person.
 *
 * The screen that makes the module's commercial purpose real rather than aspirational.
 * Sorento sells through dealers and therefore does not know who owns its products; S1 built
 * the ledger, S2 the engine, S3 the journey that fills them, and this is where a human
 * finally sees the result.
 *
 * **Every section always renders, even when empty** (CRUD UX standard). A consumer with no
 * purchases is a normal, common state - it is exactly what a provisional profile looks like -
 * and hiding the section would leave a CS agent unsure whether the data is missing or the
 * page is broken. Each empty state says what would put something there.
 *
 * **Purchase value is absent, not null, without the permission** (AC-L24), and the seed
 * grants that permission to nobody, so the absent case is the one this page renders by
 * default. It says "hidden" rather than drawing a blank or a zero: a zero would tell a CS
 * agent the dealer sold it for nothing.
 */

import { use } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateInMalaysia } from '@/lib/helpers';
import { statusPillClass } from '@/lib/status-pill';

import {
  getConsumer360,
  type ConsumerComplaint,
  type ConsumerPurchase,
} from '../services/consumerService';

export default function Consumer360Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const query = useQuery({
    queryKey: ['consumer-360', id],
    queryFn: () => getConsumer360(id),
  });

  if (query.isLoading) {
    return (
      <div className="flex flex-col gap-4 p-5">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (query.isError || !query.data) {
    return (
      <div className="p-5">
        <Card>
          <CardContent className="p-6 text-sm text-destructive">
            Could not load this consumer.
          </CardContent>
        </Card>
      </div>
    );
  }

  const { profile, merged_into_id, purchases, complaints } = query.data;

  // AC-L10. The losing side of a merge is retained pointing at the survivor precisely so
  // this question is answerable - a 404 would read as "the record was deleted".
  if (merged_into_id) {
    return (
      <div className="flex flex-col gap-4 p-5">
        <h1 className="text-xl font-semibold">This consumer was merged</h1>
        <Card>
          <CardContent className="flex flex-col items-start gap-3 p-6">
            <p className="text-sm text-muted-foreground">
              Their purchases and history moved to another profile.
            </p>
            <Button asChild>
              <Link href={`/consumer-management/consumers/${merged_into_id}`}>
                Open the surviving profile
              </Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5 p-5">
      {/* Wraps on mobile: a long name beside action buttons in a non-wrapping flex row
          overlaps AND forces page-wide horizontal overflow. */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-2">
          <Button asChild variant="ghost" size="sm" className="h-8 px-2">
            <Link href="/consumer-management/consumers">
              <ArrowLeft className="size-4" />
            </Link>
          </Button>
          <div className="min-w-0">
            <h1 className="min-w-0 text-xl font-semibold break-words">
              {profile.full_name || 'Name not recorded'}
            </h1>
            <p className="text-sm text-muted-foreground">{profile.phone_e164 || 'No phone'}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {profile.is_provisional ? (
            <Badge variant="secondary">Provisional</Badge>
          ) : (
            <Badge variant="outline">Confirmed</Badge>
          )}
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Consent</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-3">
          {/* Which wording they were shown, and when. The only answerable form of "did
              this person consent" - PDPA s.7(2) requires the notice in both languages, so
              "they agreed" without a version says nothing. */}
          <Field label="Purpose" value={profile.consent_purpose} />
          <Field
            label="Notice version"
            value={profile.consent_notice_version}
            empty="Not recorded - this profile was created by staff, where no notice is shown."
          />
          <Field
            label="Recorded"
            value={
              profile.consent_recorded_at
                ? formatDateInMalaysia(profile.consent_recorded_at)
                : null
            }
            empty="Never"
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Purchases ({purchases.length})</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {purchases.length === 0 ? (
            <EmptyState
              title="No purchases recorded yet."
              hint="A purchase arrives with a receipt - either the consumer lodges one through the portal, or staff record it against this phone."
            />
          ) : (
            purchases.map((purchase) => (
              <PurchaseCard key={purchase.id} purchase={purchase} />
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Complaints ({complaints.length})</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {complaints.length === 0 ? (
            <EmptyState
              title="No complaints from this consumer."
              hint="Complaints reach this page through a purchase line or through the phone number on the complaint itself."
            />
          ) : (
            complaints.map((complaint) => (
              <ComplaintRow key={complaint.id} complaint={complaint} />
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Field({
  label,
  value,
  empty = 'Not recorded',
}: {
  label: string;
  value: string | null | undefined;
  empty?: string;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className={value ? 'text-sm' : 'text-sm text-muted-foreground'}>
        {value || empty}
      </span>
    </div>
  );
}

function EmptyState({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-dashed p-6 text-center">
      <p className="text-sm font-medium">{title}</p>
      <p className="text-sm text-muted-foreground">{hint}</p>
    </div>
  );
}

function PurchaseCard({ purchase }: { purchase: ConsumerPurchase }) {
  // `undefined` means "you may not see it"; `null` means "the receipt showed no total".
  // Two different sentences, because conflating them tells a CS agent something false.
  const valueHidden = !('total_value' in purchase);

  return (
    <div className="flex flex-col gap-2 rounded-lg border p-4">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <p className="font-medium">{purchase.purchase_number || 'Purchase'}</p>
          <p className="text-sm text-muted-foreground">
            {purchase.purchase_date
              ? formatDateInMalaysia(purchase.purchase_date)
              : 'No purchase date'}
            {purchase.dealer_document_number
              ? ` - dealer document ${purchase.dealer_document_number}`
              : ''}
          </p>
        </div>
        <span className="text-sm text-muted-foreground">
          {valueHidden
            ? 'Value hidden'
            : purchase.total_value == null
              ? 'No total on the receipt'
              : `${purchase.currency || ''} ${purchase.total_value}`.trim()}
        </span>
      </div>

      {purchase.dedupe_pending ? (
        <p className="text-xs text-muted-foreground">
          Flagged for review: this receipt did not carry enough to dedupe on.
        </p>
      ) : null}

      <div className="flex flex-col gap-1">
        {purchase.lines.length === 0 ? (
          <span className="text-sm text-muted-foreground">No items recorded.</span>
        ) : (
          purchase.lines.map((line) => (
            <div key={line.id} className="flex items-center justify-between gap-2 text-sm">
              {/* What the consumer actually said, verbatim. It is the only evidence when
                  the exact variant never resolved, which is the ordinary case. */}
              <span className="min-w-0 truncate" title={line.claimed_text ?? undefined}>
                {line.claimed_text || line.kind_code || 'Item'}
              </span>
              <span className="shrink-0 text-muted-foreground">
                {line.quantity ?? 1}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function ComplaintRow({ complaint }: { complaint: ConsumerComplaint }) {
  return (
    <Link
      href={`/complaint-management/complaints/${complaint.id}`}
      className="flex flex-col gap-1 rounded-lg border p-3 transition-colors hover:bg-muted/40 sm:flex-row sm:items-center sm:justify-between"
    >
      <div className="min-w-0">
        <p className="font-medium">{complaint.complaint_number || 'Complaint'}</p>
        <p
          className="truncate text-sm text-muted-foreground"
          title={complaint.defect_description ?? undefined}
        >
          {complaint.defect_description || 'No description'}
        </p>
      </div>
      {complaint.status ? (
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${statusPillClass(complaint.status)}`}
        >
          {complaint.status}
        </span>
      ) : null}
    </Link>
  );
}
