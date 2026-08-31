'use client';

import Link from 'next/link';
import { AlertTriangle, ListChecks, Loader2, ScanLine } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { useHasPermission, usePermissions } from '@/hooks/usePermissions';
import { formatDateTimeInMalaysia, parseDateTimeAsUTC } from '@/lib/helpers';

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
  /**
   * When a code was last adopted or undone on this reading (PLAN-flyer-code-
   * adopt.md AC-C.4). Compared against the batch's own `created_at` to say
   * "propose again" when the flyer's codes moved since the last pass. Null
   * until the first adoption, and optional so existing callers need not know
   * about it.
   */
  codeOverridesChangedAt?: string | null;
}

export function SpecProposalSection({
  readingId,
  readingStatus,
  codeOverridesChangedAt = null,
}: SpecProposalSectionProps) {
  const canWriteMaster = useHasPermission(MASTER_DATA_EDIT);
  const { isLoading: permissionsLoading } = usePermissions();
  // The route wants the product-master permission too, so without it the request
  // can only come back 403. The section still renders, saying what it is.
  const { data, isLoading, isError, error, refetch } =
    useFlyerSpecProposalsQuery(readingId, {
      enabled: canWriteMaster,
    });
  const propose = useProposeFlyerSpecs(readingId);

  const isRead = readingStatus === 'done';
  // `none` only once the server has SAID none. Before it answers, and when it
  // refuses, the section must not read as "nobody has proposed from this
  // flyer" with a live Propose button over it: the first is a flash of a
  // claim nobody made, the second is an invitation to press a button that can
  // only fail the same way.
  const status = data?.status;
  const settled = !isLoading && !isError && data !== undefined;
  const busy = propose.isPending || status === 'proposing';
  // A batch exists and has stopped moving (`proposed` or `failed`; `none` is
  // no batch and `proposing` is still running - neither is "this proposal is
  // stale"), and a code moved after the pass that made it. The hint asks for
  // Propose again; it does not say why, because it is a status line, not an
  // explanation of the feature.
  const showAdoptionHint =
    canWriteMaster &&
    settled &&
    data !== undefined &&
    (status === 'proposed' || status === 'failed') &&
    Boolean(data.created_at) &&
    Boolean(codeOverridesChangedAt) &&
    // Both stamps are naive UTC off the same backend clock; parsed as UTC on
    // purpose, because `new Date("...T10:00:00")` reads local wall time and
    // the ordering would then depend on the browser's zone the day one side
    // grows an offset.
    parseDateTimeAsUTC(codeOverridesChangedAt!).getTime() >
      parseDateTimeAsUTC(data.created_at!).getTime();

  const action = canWriteMaster ? (
    <Button
      size="sm"
      variant={status === 'none' ? 'primary' : 'outline'}
      disabled={!isRead || busy || !settled}
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
      {permissionsLoading && (
        <div
          className="flex items-center gap-3 rounded-lg border border-dashed px-4 py-6"
          data-testid="dk-fr-spec-loading"
        >
          <Loader2 className="size-5 shrink-0 animate-spin text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            Checking whether this flyer has been read for specifications.
          </p>
        </div>
      )}

      {!permissionsLoading && !canWriteMaster && (
        <Empty tone="neutral" title="No spec proposals yet">
          Reading a flyer for specifications needs the product master
          permission, which your role does not have.
        </Empty>
      )}

      {canWriteMaster && isLoading && (
        <div
          className="flex items-center gap-3 rounded-lg border border-dashed px-4 py-6"
          data-testid="dk-fr-spec-loading"
        >
          <Loader2 className="size-5 shrink-0 animate-spin text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            Checking whether this flyer has been read for specifications.
          </p>
        </div>
      )}

      {canWriteMaster && isError && (
        <div
          className="flex flex-col items-start gap-3 rounded-lg border border-destructive/40 bg-destructive/5 px-3 py-3 text-sm text-destructive"
          data-testid="dk-fr-spec-error"
        >
          <p className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            <span>
              {error instanceof Error && error.message
                ? error.message
                : 'Could not check whether this flyer has been read for specifications.'}
            </span>
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            data-testid="dk-fr-spec-error-retry"
          >
            Try again
          </Button>
        </div>
      )}

      {canWriteMaster && settled && status === 'none' && (
        <Empty
          tone="neutral"
          title="This flyer has not been read for specifications"
        >
          Reading it proposes values for the products it names. You review them
          before anything is written.
        </Empty>
      )}

      {showAdoptionHint && (
        <div
          className="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200"
          data-testid="dk-fr-spec-adoption-hint"
        >
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          <p>
            Codes were adopted or undone after this proposal. Propose again to
            reflect them.
          </p>
        </div>
      )}

      {canWriteMaster && !isError && status === 'proposing' && (
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

      {canWriteMaster && !isError && status === 'failed' && data && (
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

      {canWriteMaster && !isError && status === 'proposed' && data && (
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
