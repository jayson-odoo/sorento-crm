'use client';

import Link from 'next/link';
import { AlertTriangle, ListChecks, Loader2, ScanLine } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { useHasPermission } from '@/hooks/usePermissions';
import { formatDateTimeInMalaysia } from '@/lib/helpers';

import { proposalCountsSentence } from '../../../master-data-management/flyer-spec-proposals/lib/countsSentence';
import {
  useFlyerSpecProposalsQuery,
  useProposeFlyerSpecs,
} from '../../../master-data-management/flyer-spec-proposals/hooks/useFlyerSpecProposals';
import type { FlyerReadingStatus } from '../../services/flyerReadingService';
import { Empty, Section } from './ReportSection';

/**
 * One button, and afterwards one sentence about what the flyer says.
 *
 * The reading is where the flyer IS, so this is where somebody asks it what it
 * says about the product master - but reviewing two hundred proposed values is
 * master-data work, so nothing is decided here. The section holds the press, the
 * progress and the counts, and hands over to
 * `/master-data-management/flyer-spec-proposals/{readingId}`.
 *
 * It renders in every state, including "nobody has proposed from this flyer",
 * because a section that appears only once somebody has used it is a feature
 * nobody finds. Without the product-master permission it says what it is and
 * offers nothing: knowing the flyer has been read for specs is useful to
 * somebody who cannot write them.
 */

/** The slug that authorises a write to the product master, everywhere. */
const MASTER_DATA_EDIT = 'master_data.products.edit';

export interface SpecProposalSectionProps {
  readingId: string;
  /** The reading's own status: nothing can be read off a flyer nobody read. */
  readingStatus: FlyerReadingStatus;
}

export function SpecProposalSection({
  readingId,
  readingStatus,
}: SpecProposalSectionProps) {
  const canWriteMaster = useHasPermission(MASTER_DATA_EDIT);
  // The route wants the product-master permission too, so without it the request
  // can only come back 403. The section still renders, saying what it is.
  const { data, isLoading } = useFlyerSpecProposalsQuery(readingId, {
    enabled: canWriteMaster,
  });
  const propose = useProposeFlyerSpecs(readingId);

  const isRead = readingStatus === 'done';
  const status = data?.status ?? 'none';
  const busy = propose.isPending || status === 'proposing';

  const action = canWriteMaster ? (
    <Button
      size="sm"
      variant={status === 'none' ? 'primary' : 'outline'}
      disabled={!isRead || busy || isLoading}
      title={isRead ? undefined : 'Read the flyer first'}
      onClick={() => propose.mutate()}
      data-testid="dk-fr-spec-propose"
    >
      <ScanLine className="size-4" />
      {!isRead
        ? 'Read the flyer first'
        : status === 'none'
          ? 'Propose specs from this flyer'
          : 'Propose again'}
    </Button>
  ) : undefined;

  return (
    <Section
      id="spec-proposals"
      icon={<ListChecks className="size-4" />}
      title="Specifications the flyer states"
      description="Read once here, reviewed and written in Master Data. Nothing is written by reading."
      action={action}
    >
      {!canWriteMaster && (
        <Empty tone="neutral" title="No spec proposals yet">
          Reading a flyer for specifications needs the product master
          permission, which your role does not have.
        </Empty>
      )}

      {canWriteMaster && status === 'none' && (
        <Empty
          tone="neutral"
          title="This flyer has not been read for specifications"
        >
          Reading it proposes values for the products it names. You review them
          before anything is written.
        </Empty>
      )}

      {canWriteMaster && status === 'proposing' && (
        <div
          className="flex items-center gap-3 rounded-lg border border-dashed px-4 py-6"
          data-testid="dk-fr-spec-proposing"
        >
          <Loader2 className="size-5 shrink-0 animate-spin text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            Reading the specifications off this flyer. The counts appear here
            when it is done.
          </p>
        </div>
      )}

      {canWriteMaster && status === 'failed' && data && (
        <div
          className="flex flex-col items-start gap-3 rounded-lg border border-destructive/40 bg-destructive/5 px-3 py-3 text-sm text-destructive"
          data-testid="dk-fr-spec-failed"
        >
          <p className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            <span>
              {data.error_message ||
                'The specifications could not be read, and no reason was recorded.'}
            </span>
          </p>
          <Button
            variant="outline"
            size="sm"
            disabled={propose.isPending}
            onClick={() => propose.mutate()}
            data-testid="dk-fr-spec-retry"
          >
            Try again
          </Button>
        </div>
      )}

      {canWriteMaster && status === 'proposed' && data && (
        <div
          className="flex flex-col gap-3 rounded-lg border border-border px-3 py-3"
          data-testid="dk-fr-spec-proposed"
        >
          <p className="text-sm text-foreground">
            {data.proposal_count === 0
              ? 'This flyer states nothing the product master does not already hold.'
              : proposalCountsSentence(data)}
          </p>
          {data.applied_at && (
            <p className="text-sm text-muted-foreground">
              {data.applied_count} written{' '}
              {formatDateTimeInMalaysia(data.applied_at)}
              {data.applied_by_name ? ` by ${data.applied_by_name}` : ''}
            </p>
          )}
          <Button variant="outline" size="sm" className="w-fit" asChild>
            <Link
              href={`/master-data-management/flyer-spec-proposals/${readingId}`}
            >
              Review proposals
            </Link>
          </Button>
        </div>
      )}
    </Section>
  );
}
